from datetime import datetime
from typing import Literal
import structlog
import os
from app.models.schemas import ExportResult, ToolError, ToolErrorType

logger = structlog.get_logger(__name__)


class ExportError(Exception):
    """Custom exception for export errors."""
    pass


def _validate_export_params(session_id: str, format_type: str) -> None:
    """Validate export parameters."""
    if not session_id or len(session_id) > 100:
        raise ValueError("Invalid session ID")
    if format_type not in ["pdf", "ics"]:
        raise ValueError("Format must be pdf or ics")


async def _generate_pdf(session_id: str) -> ExportResult:
    """
    Generate PDF itinerary using reportlab.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import os
    
    # Create exports directory if it doesn't exist
    exports_dir = "exports"
    os.makedirs(exports_dir, exist_ok=True)
    
    filename = f"trip_{session_id}_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    filepath = os.path.join(exports_dir, filename)
    
    # Create PDF
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, height - 50, "Trip Itinerary")
    
    # Session ID
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Session ID: {session_id}")
    c.drawString(50, height - 100, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Note about PoC
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, height - 130, "Note: This is a PoC implementation. Full itinerary content will be added in production.")
    
    c.save()
    
    # Get file size
    file_size = os.path.getsize(filepath)
    
    # Download URL
    download_url = f"http://localhost:8000/exports/{filename}"
    
    return ExportResult(
        format="pdf",
        filename=filename,
        file_size_bytes=file_size,
        download_url=download_url
    )


async def _generate_ics(session_id: str) -> ExportResult:
    """
    Generate ICS calendar file using icalendar.
    """
    from icalendar import Calendar, Event
    import os
    
    # Create exports directory if it doesn't exist
    exports_dir = "exports"
    os.makedirs(exports_dir, exist_ok=True)
    
    filename = f"trip_{session_id}_{datetime.now().strftime('%Y-%m-%d')}.ics"
    filepath = os.path.join(exports_dir, filename)
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//Trip Planner AI//trip-planner-ai//')
    cal.add('version', '2.0')
    
    # Add a sample event (in production, this would come from itinerary)
    event = Event()
    event.add('summary', 'Trip Itinerary')
    event.add('dtstart', datetime.now())
    event.add('dtend', datetime.now())
    event.add('description', f'Trip for session {session_id}')
    cal.add_component(event)
    
    # Write to file
    with open(filepath, 'wb') as f:
        f.write(cal.to_ical())
    
    # Get file size
    file_size = os.path.getsize(filepath)
    
    # Download URL
    download_url = f"http://localhost:8000/exports/{filename}"
    
    return ExportResult(
        format="ics",
        filename=filename,
        file_size_bytes=file_size,
        download_url=download_url
    )


async def export_itinerary(
    session_id: str,
    format_type: Literal["pdf", "ics"] = "pdf"
) -> ExportResult | ToolError:
    """
    Export itinerary to PDF or ICS format.
    
    Args:
        session_id: Session identifier
        format_type: Export format (pdf or ics)
    
    Returns:
        ExportResult or ToolError on failure
    """
    try:
        # Validate parameters
        _validate_export_params(session_id, format_type)
        
        # Generate file based on format
        if format_type == "pdf":
            result = await _generate_pdf(session_id)
        else:  # ics
            result = await _generate_ics(session_id)
        
        logger.info(
            "itinerary_exported",
            session_id=session_id,
            format_type=format_type,
            filename=result.filename
        )
        
        return result
        
    except ValueError as e:
        logger.warning("invalid_export_params", error=str(e))
        return ToolError(
            error_type=ToolErrorType.INVALID_PARAMS,
            message=str(e),
            retryable=False,
            tool_name="export_itinerary"
        )
    except Exception as e:
        logger.error("export_internal_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.EXPORT_FAILED,
            message="Failed to export itinerary",
            retryable=False,
            tool_name="export_itinerary"
        )
