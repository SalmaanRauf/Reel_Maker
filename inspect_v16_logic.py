#!/usr/bin/env python3
import json
from pathlib import Path
from build_clip1_v16 import (
    load_transcript, get_words, group_words_into_lines, 
    calculate_line_positions, generate_highlight_filters,
    CAPTION_Y_LINE1
)

START, END = 3938.0, 3984.0

def inspect():
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    lines = group_words_into_lines(words)
    
    first_line = lines[0]
    print(f"First Line Raw: {first_line}")
    
    y = CAPTION_Y_LINE1
    positioned = calculate_line_positions(first_line, y)
    print(f"Positioned Line 1: {positioned}")
    
    filters = generate_highlight_filters([first_line])
    print(f"Generated Filter Snippet: {filters[:500]}")

if __name__ == "__main__":
    inspect()
