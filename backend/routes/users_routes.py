import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlmodel import select
from db.user_emails import UserEmails
from utils.config_utils import get_settings
from session.session_layer import validate_session
from routes.email_routes import query_emails
import database
from slowapi import Limiter
from slowapi.util import get_remote_address
from utils.job_utils import normalize_job_title
from datetime import datetime, timedelta
from collections import defaultdict

# Logger setup
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()
APP_URL = settings.APP_URL

api_call_finished = False

# FastAPI router for email routes
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.get("/get-response-rate")   
@limiter.limit("2/minute")    
def response_rate_by_job_title(request: Request, db_session: database.DBSession, user_id: str = Depends(validate_session)):
    
    try:
        logger.info(f"Starting response rate calculation for user_id: {user_id}")
        
        # Get job related email data from DB
        user_emails = query_emails(request, db_session=db_session, user_id=user_id)
        logger.info(f"Retrieved {len(user_emails)} emails for user_id: {user_id}")

        # Create unique application IDs based on company_name only (ignore job_title for now)
        applications = {}
        
        for email in user_emails:
            if email.company_name:
                app_id = email.company_name  # Use only company name as unique identifier
                
                if app_id not in applications:
                    applications[app_id] = {
                        "company": email.company_name,
                        "job_title": email.job_title,
                        "normalized_job_title": getattr(email, 'normalized_job_title', ''),
                        "statuses": set()
                    }
                
                if email.application_status:
                    status = email.application_status.strip().lower()
                    # Ignore "unknown" statuses
                    if status != "unknown":
                        applications[app_id]["statuses"].add(status)

        logger.info(f"Created {len(applications)} unique applications for user_id: {user_id}")

        # Filter out applications that only have unknown statuses (no valid statuses)
        valid_applications = {}
        for app_id, app_data in applications.items():
            if app_data["statuses"]:  # Only include applications that have at least one valid status
                valid_applications[app_id] = app_data

        logger.info(f"Filtered to {len(valid_applications)} valid applications for user_id: {user_id}")

        # Group applications by normalized job title
        job_title_applications = {}
        
        for app_id, app_data in valid_applications.items():
            job_title = app_data["job_title"]
            normalized_job_title = app_data.get("normalized_job_title", "")
            
            # Skip applications with "unknown" job titles
            if job_title and job_title.lower() != "unknown":
                # Use normalized job title if available, otherwise normalize on-the-fly
                if normalized_job_title and normalized_job_title.strip():
                    display_title = normalized_job_title.title()  # Ensure capitalization
                    logger.debug(f"Using stored normalized title: '{job_title}' -> '{display_title}'")
                else:
                    # Fall back to on-the-fly normalization for backward compatibility
                    try:
                        logger.debug(f"Normalizing job title on-the-fly: '{job_title}'")
                        normalized_title = normalize_job_title(job_title)
                        # Only use normalized title if it's valid (not None or empty)
                        if normalized_title and normalized_title.strip():
                            display_title = normalized_title  # Already capitalized by normalize_job_title
                            logger.debug(f"On-the-fly normalization successful: '{job_title}' -> '{display_title}'")
                        else:
                            display_title = job_title.title()  # Fall back to capitalized original
                            logger.debug(f"Normalization returned empty, using capitalized original: '{job_title}' -> '{display_title}'")
                    except Exception as e:
                        logger.warning(f"Failed to normalize job title '{job_title}': {e}")
                        display_title = job_title.title()  # Fall back to capitalized original
                
                if display_title not in job_title_applications:
                    job_title_applications[display_title] = {
                        "total": 0,
                        "responses": 0
                    }
                
                job_title_applications[display_title]["total"] += 1
                
                # Check if this application received any response beyond initial confirmation/rejection
                statuses = app_data["statuses"]
                has_response = any(status not in ["application confirmation", "rejection"] for status in statuses)
                
                if has_response:
                    job_title_applications[display_title]["responses"] += 1

        logger.info(f"Grouped into {len(job_title_applications)} job title categories for user_id: {user_id}")

        # Calculate response rates for each job title
        response_rate = []
        for job_title, data in job_title_applications.items():
            rate = round((data["responses"] / data["total"]) * 100, 2)
            response_rate.append({
                "title": job_title,
                "rate": rate
            })
            logger.debug(f"Job title '{job_title}': {data['responses']}/{data['total']} = {rate}% response rate")

        logger.info(f"Calculated response rates for {len(response_rate)} job titles for user_id: {user_id}")
        return response_rate
    
    except Exception as e:
        logger.error(f"Error fetching job titles for user_id {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@router.get("/user-response-rate")
def calculate_response_rate(
    request: Request, db_session: database.DBSession, user_id: str = Depends(validate_session)
) -> dict:
    db_session.expire_all()  # Clear any cached data
    db_session.commit()  # Commit pending changes to ensure the database is in latest state
    user_emails = db_session.exec(
        select(UserEmails).where(UserEmails.user_id == user_id)
    ).all()

    # if user has no emails just return 0.0
    if not user_emails:
        return {"value": 0.0}

    # Create unique application IDs based on company_name only (ignore job_title for now)
    applications = {}
    
    for email in user_emails:
        if email.company_name:
            app_id = email.company_name  # Use only company name as unique identifier
            
            if app_id not in applications:
                applications[app_id] = {
                    "company": email.company_name,
                    "job_title": email.job_title,
                    "statuses": set(),
                    "received_at": email.received_at
                }
            
            if email.application_status:
                status = email.application_status.strip().lower()
                # Ignore "unknown" statuses
                if status != "unknown":
                    applications[app_id]["statuses"].add(status)

    logger.info(f"DEBUG: All applications before filtering: {len(applications)}")

    # Filter out applications that only have unknown statuses (no valid statuses)
    valid_applications = {}
    for app_id, app_data in applications.items():
        if app_data["statuses"]:  # Only include applications that have at least one valid status
            valid_applications[app_id] = app_data

    # Calculate response rate
    total_applications = len(valid_applications)
    if total_applications == 0:
        return {"value": 0.0}

    # Count applications that received a response (not just application confirmation or rejection)
    responses_received = 0
    
    for app_id, app_data in valid_applications.items():
        statuses = app_data["statuses"]
        
        # Check if this application received any response beyond initial confirmation/rejection
        has_response = any(status not in ["application confirmation", "rejection"] for status in statuses)
        
        if has_response:
            responses_received += 1

    response_rate_percent = (responses_received / total_applications) * 100
    return {"value": round(response_rate_percent, 1)}

@router.get("/dashboard-metrics")
@limiter.limit("5/minute")
def get_dashboard_metrics(
    request: Request, db_session: database.DBSession, user_id: str = Depends(validate_session)
) -> dict:
    """
    Get comprehensive dashboard metrics for the user's job search.
    Returns metrics including total applications, interview rate, offer rate,
    applications by status, time-based metrics, and more.
    """
    try:
        logger.info(f"Calculating dashboard metrics for user_id: {user_id}")

        # Get all user emails
        user_emails = db_session.exec(
            select(UserEmails).where(UserEmails.user_id == user_id)
        ).all()

        if not user_emails:
            return {
                "total_applications": 0,
                "interview_rate": 0.0,
                "offer_rate": 0.0,
                "avg_time_to_response": 0.0,
                "applications_last_7_days": 0,
                "applications_last_30_days": 0,
                "active_applications": 0,
                "applications_by_status": {},
                "applications_per_week": [],
                "applications_per_month": []
            }

        # Filter out false positives and count total applications
        valid_emails = [
            email for email in user_emails
            if email.application_status.strip().lower() != "false positive"
        ]

        total_applications = len(valid_emails)

        # Calculate time-based metrics
        now = datetime.now()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        applications_last_7_days = sum(
            1 for email in valid_emails
            if email.received_at and email.received_at.replace(tzinfo=None) >= seven_days_ago
        )

        applications_last_30_days = sum(
            1 for email in valid_emails
            if email.received_at and email.received_at.replace(tzinfo=None) >= thirty_days_ago
        )

        # Group by company to get unique applications
        applications_by_company = defaultdict(lambda: {
            "statuses": set(),
            "received_dates": [],
            "company": "",
            "job_title": ""
        })

        for email in valid_emails:
            if email.company_name:
                app_id = email.company_name
                applications_by_company[app_id]["statuses"].add(
                    email.application_status.strip().lower()
                )
                applications_by_company[app_id]["received_dates"].append(email.received_at)
                applications_by_company[app_id]["company"] = email.company_name
                applications_by_company[app_id]["job_title"] = email.job_title

        # Calculate status breakdown
        status_counts = defaultdict(int)
        for email in valid_emails:
            status = email.application_status.strip()
            status_counts[status] += 1

        # Calculate interview rate
        interview_statuses = {"interview invitation", "assessment sent"}
        num_interviews = sum(
            1 for app in applications_by_company.values()
            if any(status in interview_statuses for status in app["statuses"])
        )
        interview_rate = (num_interviews / len(applications_by_company)) * 100 if applications_by_company else 0.0

        # Calculate offer rate
        num_offers = sum(
            1 for app in applications_by_company.values()
            if "offer made" in app["statuses"]
        )
        offer_rate = (num_offers / len(applications_by_company)) * 100 if applications_by_company else 0.0

        # Calculate average time to response (from application confirmation to any other response)
        time_to_responses = []
        for app in applications_by_company.values():
            if "application confirmation" in app["statuses"] and len(app["statuses"]) > 1:
                dates = sorted([d for d in app["received_dates"] if d])
                if len(dates) >= 2:
                    # Time from first email to second email (assumed response)
                    time_diff = (dates[1] - dates[0]).total_seconds() / 86400  # Convert to days
                    if time_diff > 0:
                        time_to_responses.append(time_diff)

        avg_time_to_response = sum(time_to_responses) / len(time_to_responses) if time_to_responses else 0.0

        # Calculate active applications (not rejected, not offered, not withdrew)
        inactive_statuses = {"rejection", "offer made", "withdrew application", "hiring freeze notification"}
        active_applications = sum(
            1 for app in applications_by_company.values()
            if not any(status in inactive_statuses for status in app["statuses"])
        )

        # Calculate applications per week (last 12 weeks)
        weekly_counts = defaultdict(int)
        for email in valid_emails:
            if email.received_at:
                # Calculate ISO week number
                week_key = email.received_at.isocalendar()[:2]  # (year, week)
                week_label = f"{week_key[0]}-W{week_key[1]:02d}"
                weekly_counts[week_label] += 1

        # Get last 12 weeks
        applications_per_week = []
        for i in range(11, -1, -1):
            week_date = now - timedelta(weeks=i)
            week_key = week_date.isocalendar()[:2]
            week_label = f"{week_key[0]}-W{week_key[1]:02d}"
            applications_per_week.append({
                "week": week_label,
                "count": weekly_counts.get(week_label, 0)
            })

        # Calculate applications per month (last 6 months)
        monthly_counts = defaultdict(int)
        for email in valid_emails:
            if email.received_at:
                month_key = email.received_at.strftime("%Y-%m")
                monthly_counts[month_key] += 1

        # Get last 6 months
        applications_per_month = []
        for i in range(5, -1, -1):
            month_date = now - timedelta(days=30*i)
            month_key = month_date.strftime("%Y-%m")
            month_label = month_date.strftime("%b %Y")
            applications_per_month.append({
                "month": month_label,
                "count": monthly_counts.get(month_key, 0)
            })

        logger.info(f"Successfully calculated metrics for user_id: {user_id}")

        return {
            "total_applications": total_applications,
            "interview_rate": round(interview_rate, 1),
            "offer_rate": round(offer_rate, 1),
            "avg_time_to_response": round(avg_time_to_response, 1),
            "applications_last_7_days": applications_last_7_days,
            "applications_last_30_days": applications_last_30_days,
            "active_applications": active_applications,
            "applications_by_status": dict(status_counts),
            "applications_per_week": applications_per_week,
            "applications_per_month": applications_per_month
        }

    except Exception as e:
        logger.error(f"Error calculating dashboard metrics for user_id {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

