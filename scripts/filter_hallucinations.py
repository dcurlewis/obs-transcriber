#!/usr/bin/env python3
"""
Whisper Hallucination Filter
Removes obvious hallucinations from SRT files like repeated "Thank you" during silence
"""

import sys
import re
from pathlib import Path
import srt

def is_hallucination(subtitle, previous_subtitle=None):
    """
    Detect if a subtitle entry is likely a hallucination
    """
    text = subtitle.content.strip().lower()
    
    # Common hallucination phrases (mostly from YouTube training data)
    hallucination_patterns = [
        r'^thank you\.?$',
        r'^thanks\.?$', 
        r'^thank you very much\.?$',
        r'^thanks for watching\.?$',
        r'^don\'t forget to like and subscribe\.?$',
        r'^subscribe\.?$',
        r'^like and subscribe\.?$',
        r'^\.+$',  # Just periods
        r'^$',     # Empty
    ]
    
    # Check against hallucination patterns
    for pattern in hallucination_patterns:
        if re.match(pattern, text):
            return True
    
    # Check for very short isolated words during long gaps
    if previous_subtitle:
        gap = subtitle.start - previous_subtitle.end
        if gap.total_seconds() > 20 and len(text.split()) <= 2:
            return True
    
    # Check for repetitive content (same text appearing frequently)
    if len(text) < 20 and text in ['thank you', 'thanks', 'yes', 'no', 'okay', 'ok']:
        return True
        
    return False

def filter_srt_file(input_file, output_file=None):
    """
    Filter hallucinations from an SRT file
    """
    if not output_file:
        # Create output filename with _filtered suffix
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_filtered{input_path.suffix}"
    
    # Read SRT file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        subtitles = list(srt.parse(content))
        print(f"📄 Original subtitles: {len(subtitles)} entries")
        
    except Exception as e:
        print(f"❌ Error reading {input_file}: {e}")
        return False
    
    # Filter hallucinations
    filtered_subtitles = []
    removed_count = 0
    previous_subtitle = None
    
    for subtitle in subtitles:
        if is_hallucination(subtitle, previous_subtitle):
            removed_count += 1
            print(f"🗑️  Removed hallucination: '{subtitle.content.strip()}'")
        else:
            # Re-index the subtitle
            subtitle.index = len(filtered_subtitles) + 1
            filtered_subtitles.append(subtitle)
            previous_subtitle = subtitle
    
    print(f"✅ Filtered subtitles: {len(filtered_subtitles)} entries")
    print(f"🎯 Removed {removed_count} hallucinations")
    
    # Write filtered SRT file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(srt.compose(filtered_subtitles))
        
        print(f"💾 Saved filtered file: {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ Error writing {output_file}: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python filter_hallucinations.py <input.srt> [output.srt]")
        print("\nFilters obvious hallucinations from Whisper SRT files")
        print("If no output file specified, creates <input>_filtered.srt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(input_file).exists():
        print(f"❌ Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"🧹 Filtering hallucinations from: {input_file}")
    
    if filter_srt_file(input_file, output_file):
        print("✅ Filtering complete!")
    else:
        print("❌ Filtering failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 