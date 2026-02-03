#!/usr/bin/env python3
"""
Google Calendar integration via local macOS Calendar.app
Uses EventKit to read calendar data that's already synced to your Mac
"""

import os
import sys
from datetime import datetime, timedelta
import pytz
from tzlocal import get_localzone

# Try to import EventKit (macOS only)
try:
    from EventKit import (
        EKEventStore, EKEntityTypeEvent,
        EKParticipantStatusAccepted, EKParticipantStatusTentative
    )
    from Foundation import NSDate, NSCalendar, NSDateComponents
    EVENTKIT_AVAILABLE = True
except ImportError:
    EVENTKIT_AVAILABLE = False
    print("EventKit not available (are you on macOS?)")


class CalendarService:
    """Service for fetching meetings from macOS Calendar.app"""
    
    def __init__(self):
        self.event_store = None
        # Automatically detect system timezone
        try:
            self.local_tz = get_localzone()
        except Exception:
            # Fallback to UTC if detection fails
            self.local_tz = pytz.UTC
        
        if EVENTKIT_AVAILABLE:
            self._initialize_event_store()
    
    def _initialize_event_store(self):
        """Initialize EventKit event store and request calendar access"""
        self.event_store = EKEventStore.alloc().init()
        
        # Request access to calendars (will prompt user first time)
        # Note: This is synchronous in newer macOS versions
        granted = self.event_store.requestFullAccessToEventsWithCompletion_(None)
        
        if not granted:
            print("Calendar access not granted. The app needs permission to read your calendar.")
            print("Go to System Settings > Privacy & Security > Calendars and enable access.")
    
    def get_meetings_for_date(self, target_date=None):
        """
        Fetch meetings for a specific date from macOS Calendar.app
        If target_date is None, uses today
        Returns a list of meeting dictionaries
        """
        if not EVENTKIT_AVAILABLE:
            return []
        
        if not self.event_store:
            return []
        
        try:
            # Use target date or today
            now = datetime.now()
            if target_date is None:
                target_date = now
            
            # Get start and end of the target date
            day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Convert to NSDate for EventKit
            start_date = NSDate.dateWithTimeIntervalSince1970_(day_start.timestamp())
            end_date = NSDate.dateWithTimeIntervalSince1970_(day_end.timestamp())
            
            # Get all calendars
            calendars = self.event_store.calendarsForEntityType_(EKEntityTypeEvent)
            
            # Create predicate for today's events
            predicate = self.event_store.predicateForEventsWithStartDate_endDate_calendars_(
                start_date, end_date, calendars
            )
            
            # Fetch events
            events = self.event_store.eventsMatchingPredicate_(predicate)
            
            meetings = []
            
            for event in events:
                # Skip all-day events
                if event.isAllDay():
                    continue
                
                # Get event details
                title = str(event.title()) if event.title() else "Untitled Meeting"
                start_date = event.startDate()
                end_date = event.endDate()
                
                # Convert NSDate to Python datetime (timezone-aware)
                start_dt = datetime.fromtimestamp(start_date.timeIntervalSince1970(), tz=self.local_tz)
                end_dt = datetime.fromtimestamp(end_date.timeIntervalSince1970(), tz=self.local_tz)
                
                # Determine if meeting is current or past
                now_aware = now.replace(tzinfo=self.local_tz) if now.tzinfo is None else now
                is_current = start_dt <= now_aware <= end_dt
                is_past = end_dt < now_aware
                
                # Skip past meetings that ended more than 4 hours ago
                if is_past:
                    hours_since_end = (now_aware - end_dt).total_seconds() / 3600
                    if hours_since_end > 4:
                        continue
                
                # Check attendee count (excluding self)
                attendees = event.attendees() if event.attendees() else []
                attendee_count = len(attendees)
                
                # Debug logging for attendee information
                import os
                if os.environ.get('DEBUG_CALENDAR') == 'true':
                    print(f"[DEBUG] Event: {title}")
                    print(f"[DEBUG]   Start: {start_dt}")
                    print(f"[DEBUG]   End: {end_dt}")
                    print(f"[DEBUG]   All-day: {event.isAllDay()}")
                    print(f"[DEBUG]   Attendee count: {attendee_count}")
                    for att in attendees:
                        att_name = att.name() if att.name() else "Unknown"
                        att_email = att.emailAddress() if att.emailAddress() else "No email"
                        print(f"[DEBUG]   - {att_name} ({att_email})")
                
                # Skip events where I am the only attendee (personal reminders, placeholders)
                # Check if there are any attendees that are NOT me
                other_attendees = []
                for att in attendees:
                    email = str(att.emailAddress()).lower() if att.emailAddress() else ""
                    # Filter out my own email
                    if email and "dbdave@canva.com" not in email:
                        other_attendees.append(att)
                
                # Skip if no other attendees besides myself
                if len(other_attendees) == 0:
                    if os.environ.get('DEBUG_CALENDAR') == 'true':
                        print(f"[DEBUG]   -> Skipped: No other attendees besides dbdave@canva.com")
                    continue
                
                # Look for Zoom link specifically (only Zoom is used)
                import re
                has_conference = False
                conference_url = None
                
                # First check the event URL field
                if event.URL():
                    url = str(event.URL())
                    if 'zoom.us' in url.lower():
                        has_conference = True
                        conference_url = url
                
                # If not found in URL, search notes for Zoom link
                if not has_conference and event.notes():
                    notes = str(event.notes())
                    # Look for zoom.us URLs specifically
                    zoom_match = re.search(r'https?://[^\s<>"]*zoom\.us[^\s<>"]*', notes, re.IGNORECASE)
                    if zoom_match:
                        has_conference = True
                        conference_url = zoom_match.group(0)
                        # Clean up URL (remove trailing punctuation)
                        conference_url = conference_url.rstrip('.,;:)')
                
                # If still not found, try to find it in the location field
                if not has_conference and event.location():
                    location = str(event.location())
                    if 'zoom.us' in location.lower():
                        zoom_match = re.search(r'https?://[^\s<>"]*zoom\.us[^\s<>"]*', location, re.IGNORECASE)
                        if zoom_match:
                            has_conference = True
                            conference_url = zoom_match.group(0)
                            conference_url = conference_url.rstrip('.,;:)')
                
                # Extract attendee names for transcript header (only accepted/tentative attendees)
                # EKParticipantStatusAccepted = 2, EKParticipantStatusTentative = 4
                attendee_names = []
                for att in other_attendees:
                    status = att.participantStatus()
                    # Only include attendees who accepted or marked tentative
                    if status in (EKParticipantStatusAccepted, EKParticipantStatusTentative):
                        name = str(att.name()) if att.name() else str(att.emailAddress()).split('@')[0]
                        attendee_names.append(name)
                
                meetings.append({
                    'id': str(event.eventIdentifier()),
                    'name': title,
                    'start': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'end': end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                    'start_time': start_dt.strftime('%I:%M %p'),
                    'end_time': end_dt.strftime('%I:%M %p'),
                    'is_current': is_current,
                    'is_past': is_past,
                    'has_conference': has_conference,
                    'conference_url': conference_url,
                    'attendee_count': attendee_count,
                    'attendees': attendee_names
                })
            
            # Sort by start time
            meetings.sort(key=lambda x: x['start'])
            
            return meetings
            
        except Exception as e:
            print(f'Error fetching calendar events: {e}')
            import traceback
            traceback.print_exc()
            return []
    
    def get_todays_meetings(self):
        """
        Fetch today's meetings (backward compatibility wrapper)
        """
        return self.get_meetings_for_date()