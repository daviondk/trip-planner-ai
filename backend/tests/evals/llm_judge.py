"""
LLM-as-Judge implementation for quality evaluation.

Uses LLM to evaluate the quality of agent responses based on predefined criteria.
"""
import asyncio
from typing import Dict, List, Any
import structlog
from app.config.settings import settings
import httpx

logger = structlog.get_logger(__name__)


class LLMJudge:
    """LLM-as-Judge for evaluating response quality."""
    
    def __init__(self):
        self.api_key = settings.YANDEX_GPT_API_KEY
        self.folder_id = settings.YANDEX_GPT_FOLDER_ID
        self.model = settings.YANDEX_GPT_MODEL
    
    async def _call_llm(self, prompt: str) -> str:
        """Call YandexGPT API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "modelUri": f"gpt://{self.folder_id}/{self.model}",
                    "completionOptions": {
                        "stream": False,
                        "temperature": 0.3,
                        "maxTokens": 1000
                    },
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an impartial judge evaluating the quality of AI responses. Rate responses on a scale of 1-5 for each criterion."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def evaluate_response(
        self,
        query: str,
        response: str,
        criteria: List[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a response using LLM-as-Judge.
        
        Args:
            query: Original user query
            response: Agent's response
            criteria: List of evaluation criteria
        
        Returns:
            Dictionary with scores and reasoning
        """
        if criteria is None:
            criteria = [
                "relevance",  # How relevant is the response to the query
                "completeness",  # Does it address all aspects of the query
                "accuracy",  # Is the information accurate
                "helpfulness",  # Is the response useful
                "clarity"  # Is the response clear and well-structured
            ]
        
        prompt = f"""
Evaluate the following AI response based on these criteria: {', '.join(criteria)}.

User Query: {query}

AI Response: {response}

Provide your evaluation in the following JSON format:
{{
    "scores": {{
        "relevance": <1-5>,
        "completeness": <1-5>,
        "accuracy": <1-5>,
        "helpfulness": <1-5>,
        "clarity": <1-5>
    }},
    "average_score": <1-5>,
    "reasoning": "<brief explanation of scores>",
    "issues": ["<list of any issues found>"]
}}
"""
        
        try:
            llm_output = await self._call_llm(prompt)
            
            # Parse JSON from LLM output
            import json
            # Try to extract JSON from response
            start_idx = llm_output.find('{')
            end_idx = llm_output.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = llm_output[start_idx:end_idx]
                evaluation = json.loads(json_str)
            else:
                # Fallback if JSON parsing fails
                evaluation = {
                    "scores": {"relevance": 3, "completeness": 3, "accuracy": 3, "helpfulness": 3, "clarity": 3},
                    "average_score": 3.0,
                    "reasoning": "Failed to parse LLM output",
                    "issues": []
                }
            
            logger.info(
                "llm_judge_evaluation",
                average_score=evaluation.get("average_score"),
                reasoning=evaluation.get("reasoning")[:100]
            )
            
            return evaluation
            
        except Exception as e:
            logger.error("llm_judge_error", error=str(e))
            return {
                "scores": {"relevance": 0, "completeness": 0, "accuracy": 0, "helpfulness": 0, "clarity": 0},
                "average_score": 0.0,
                "reasoning": f"Evaluation failed: {str(e)}",
                "issues": ["Evaluation error"]
            }
    
    async def evaluate_itinerary(
        self,
        itinerary: List[Dict[str, Any]],
        preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate an itinerary against user preferences.
        
        Args:
            itinerary: Generated itinerary
            preferences: User preferences
        
        Returns:
            Dictionary with evaluation scores
        """
        itinerary_str = str(itinerary)
        preferences_str = str(preferences)
        
        prompt = f"""
Evaluate this itinerary against the user preferences:

User Preferences: {preferences_str}

Generated Itinerary: {itinerary_str}

Evaluate on these criteria:
- alignment: How well does the itinerary match user preferences (1-5)
- variety: Is there good variety in activities (1-5)
- feasibility: Is the itinerary realistic and achievable (1-5)
- completeness: Does it cover all requested aspects (1-5)

Provide JSON output:
{{
    "alignment": <1-5>,
    "variety": <1-5>,
    "feasibility": <1-5>,
    "completeness": <1-5>,
    "average_score": <1-5>,
    "reasoning": "<explanation>",
    "suggestions": ["<list of improvements>"]
}}
"""
        
        try:
            llm_output = await self._call_llm(prompt)
            
            start_idx = llm_output.find('{')
            end_idx = llm_output.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = llm_output[start_idx:end_idx]
                evaluation = json.loads(json_str)
            else:
                evaluation = {
                    "alignment": 3, "variety": 3, "feasibility": 3, "completeness": 3,
                    "average_score": 3.0,
                    "reasoning": "Failed to parse",
                    "suggestions": []
                }
            
            return evaluation
            
        except Exception as e:
            logger.error("itinerary_evaluation_error", error=str(e))
            return {
                "alignment": 0, "variety": 0, "feasibility": 0, "completeness": 0,
                "average_score": 0.0,
                "reasoning": f"Evaluation failed: {str(e)}",
                "suggestions": []
            }


# Global judge instance
llm_judge = LLMJudge()
