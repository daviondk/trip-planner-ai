"""
Run evaluation suite against golden test dataset.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from datetime import date, timedelta
from langchain_core.messages import HumanMessage
from app.models.schemas import TripPlannerState, UserPreferences, TravelerGroup, BudgetInfo
from app.agents.orchestrator import trip_planner_graph
from tests.evals.golden_dataset import GOLDEN_TESTS, run_regression_test


async def run_single_test(test_case):
    """Run a single test case."""
    state = TripPlannerState(
        messages=[HumanMessage(content=test_case["query"])],
        session_id=f"eval_{test_case['id']}",
        user_preferences=None,
        current_intent=None,
        itinerary_draft=[],
        booking_candidates=[],
        map_data=None,
        agent_outputs={},
        iteration_count=0,
        error_context=[],
        retrieval_degraded=False,
        is_blocked=False,
        llm_degraded=False,
        booking_degraded=False,
        maps_degraded=False,
        token_count=0,
        created_at=date.today(),
        last_activity_at=date.today()
    )
    
    try:
        config = {"configurable": {"thread_id": f"eval_{test_case['id']}"}}
        result = await trip_planner_graph.ainvoke(state, config)
        
        return run_regression_test(result, test_case)
    except Exception as e:
        return {
            "test_id": test_case["id"],
            "passed": False,
            "failures": [{"error": str(e)}]
        }


async def main():
    """Run all golden tests."""
    print(f"Running {len(GOLDEN_TESTS)} golden tests...\n")
    
    results = []
    for test_case in GOLDEN_TESTS:
        print(f"Running test {test_case['id']}...")
        result = await run_single_test(test_case)
        results.append(result)
        
        if result["passed"]:
            print(f"  ✓ PASSED")
        else:
            print(f"  ✗ FAILED")
            for failure in result["failures"]:
                print(f"    - {failure}")
    
    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"Pass rate: {passed/total*100:.1f}%")
    print(f"{'='*50}")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
