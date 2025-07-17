import srt
import sys
import re
from datetime import timedelta

def main():
    if len(sys.argv) != 3:
        print("Usage: python interleave.py <me_srt_file> <others_srt_file>")
        sys.exit(1)

    me_srt_file = sys.argv[1]
    others_srt_file = sys.argv[2]

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

    all_subs = sorted(me_subs + other_subs, key=lambda x: x.start)

    for sub in all_subs:
        # Format timestamp to HH:MM:SS
        timestamp = str(sub.start).split('.')[0]
        print(f"[{timestamp}] {sub.speaker}: {sub.content.strip()}")

if __name__ == "__main__":
    main() 