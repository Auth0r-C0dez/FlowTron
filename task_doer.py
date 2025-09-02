import os 
from dotenv import load_dotenv
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import datetime
import smtplib
from email.mime.text import MIMEText


load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def reading_tasks(filepath):
    with open(filepath ,"r") as f:
        return f.read()
    
def summarise_task(tasks):
    prompt = f"""
You are a task priority planner assistant.

Your role is to help users organize their tasks based on urgency, importance, duration, and stakeholder sensitivity. Classify each task into one of the following categories:

- High Priority: Urgent and important. Must be done as soon as possible.
- Medium Priority: Important but not urgent. Should be scheduled or planned.
- Low Priority: Not urgent and less important. Can be delayed or delegated.

Consider these specific rules:
1. Tasks involving customers, managers, leadership, or anything that affects public reputation must be prioritized higher, even if they are not explicitly urgent.
2. Tasks that are estimated to take longer (e.g., writing reports, preparing presentations) and have stakeholder involvement should be scheduled **earlier** to allow enough time for completion.
3. Administrative or personal development tasks (e.g., inbox cleanup, internal learning) can be deprioritized unless otherwise stated.

Your output should include only a structured list under the following headers:
High Priority:
- task 1
- task 2

Medium Priority:
- task 3
- task 4

Low Priority:
- task 5
- task 6

Tasks to analyze:
{tasks}

Do not provide any explanations. Only return the sorted task list in the format above.
"""

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return response.text

#########################################################################

def setup_google_calendar():
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)
    return service

################################################

def schedule_tasks_on_calendar(tasks_by_priority, service):
    now = datetime.datetime.utcnow()
    day_offset = {'High': 0, 'Medium': 1, 'Low': 3}

    for priority, tasks in tasks_by_priority.items():
        offset = day_offset.get(priority, 5)

        for i, task in enumerate(tasks):
            task_date = now + datetime.timedelta(days=offset + i)
            start_time = task_date.replace(hour=10, minute=0)
            end_time = task_date.replace(hour=11, minute=0)

            start = start_time.isoformat() + 'Z'
            end = end_time.isoformat() + 'Z'

            event = {
                'summary': task,
                'start': {'dateTime': start, 'timeZone': 'Asia/Kolkata'},
                'end': {'dateTime': end, 'timeZone': 'Asia/Kolkata'},
            }

            created_event = service.events().insert(calendarId='primary', body=event).execute()
            print(f"✅ Scheduled: '{task}' at {created_event['start']['dateTime']}")
  
########################################

def send_email_confirmation(recipient, subject, body):
    sender_email = os.getenv("EMAIL_ADDRESS")
    sender_password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        print("❌ Email credentials not found in .env. Skipping email.")
        return

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        
        print("✅ Email confirmation sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    # Step 1: Read tasks from file
    raw_tasks = reading_tasks("task.txt")
    
    # Step 2: Get Gemini summary
    summary = summarise_task(raw_tasks)
    print("\n🧠 Gemini Categorized Tasks:\n")
    print(summary)

    # Step 3: Parse Gemini output into dict
    def parse_tasks(summary):
        tasks_by_priority = {'High': [], 'Medium': [], 'Low': []}
        current = None
        for line in summary.splitlines():
            line = line.strip()
            if line.lower().startswith("high priority"):
                current = "High"
            elif line.lower().startswith("medium priority"):
                current = "Medium"
            elif line.lower().startswith("low priority"):
                current = "Low"
            elif line.startswith("-") and current:
                tasks_by_priority[current].append(line[2:].strip())
        return tasks_by_priority

    categorized_tasks = parse_tasks(summary)

    # Step 4: Authenticate Google Calendar
    service = setup_google_calendar()

    # Step 5: Schedule tasks
    print("\n📅 Scheduling tasks on Google Calendar...\n")
    schedule_tasks_on_calendar(categorized_tasks, service)

    # Step 6: Send email confirmation
    recipient_email = os.getenv("EMAIL_RECIPIENT", os.getenv("EMAIL_ADDRESS"))
    email_subject = "Task Scheduling Complete"
    email_body = f"Hello,\n\nYour tasks have been successfully scheduled on your Google Calendar.\n\nHere is the prioritized list:\n\n{summary}\n\nBest regards,\nTask Scheduler"
    
    send_email_confirmation(recipient_email, email_subject, email_body)