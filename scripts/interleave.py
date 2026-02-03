import srt
import sys
import re
import argparse
from datetime import datetime, timedelta


def print_header(meeting_name, meeting_date, attendees):
    """Print meeting metadata header at the top of the transcript"""
    has_header = False
    
    if meeting_name:
        print(f"Meeting: {meeting_name}")
        has_header = True
    
    if meeting_date:
        # Format: 20240204_1000 -> 2024-02-04 10:00
        try:
            dt = datetime.strptime(meeting_date, "%Y%m%d_%H%M")
            print(f"Date: {dt.strftime('%Y-%m-%d %H:%M')}")
        except ValueError:
            print(f"Date: {meeting_date}")
        has_header = True
    
    if attendees:
        # Convert pipe-delimited attendees to comma-separated
        attendee_list = attendees.replace('|', ', ')
        print(f"Attendees: {attendee_list}")
        has_header = True
    
    if has_header:
        print()
        print("---")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Interleave two SRT files into a single chronological transcript"
    )
    parser.add_argument('me_srt_file', help='SRT file for "Me" speaker')
    parser.add_argument('others_srt_file', help='SRT file for "Others" speakers')
    parser.add_argument('--meeting-name', default='', help='Name of the meeting')
    parser.add_argument('--meeting-date', default='', help='Date of the meeting (YYYYMMDD_HHMM format)')
    parser.add_argument('--attendees', default='', help='Pipe-delimited list of attendees')
    
    args = parser.parse_args()
    
    me_srt_file = args.me_srt_file
    others_srt_file = args.others_srt_file

    try:
        with open(me_srt_file, 'r', encoding='utf-8') as f:
            me_subs = list(srt.parse(f.read()))
        for sub in me_subs:
            sub.speaker = "Me"

        with open(others_srt_file, 'r', encoding='utf-8') as f:
            other_subs = list(srt.parse(f.read()))
        
        # Process others' subtitles to extract speaker info from diarization
        for sub in other_subs:
            # Look for speaker labels like "[Speaker 1]" at the start of content
            speaker_match = re.match(r'^\[(Speaker \d+)\]\s+(.*)', sub.content.strip())
            if speaker_match:
                # Extract the speaker label and the actual content
                speaker_label = speaker_match.group(1)
                content = speaker_match.group(2)
                sub.speaker = speaker_label
                sub.content = content
            else:
                sub.speaker = "Others"

    except FileNotFoundError as e:
        print(f"Error: {e.filename} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing SRT files: {e}")
        sys.exit(1)

    # Print meeting metadata header
    print_header(args.meeting_name, args.meeting_date, args.attendees)

    all_subs = sorted(me_subs + other_subs, key=lambda x: x.start)

    for sub in all_subs:
        # Format timestamp to HH:MM:SS
        timestamp = str(sub.start).split('.')[0]
        print(f"[{timestamp}] {sub.speaker}: {sub.content.strip()}")

if __name__ == "__main__":
    main() 