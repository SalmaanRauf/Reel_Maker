#!/usr/bin/env python3
"""
Face Detection Module for Viral Clip Generator
Uses OpenCV's Haar Cascades (reliable, no MediaPipe API issues)
"""
import cv2
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

class FaceDetector:
    """Detect and track faces in video frames using OpenCV Haar Cascades."""
    
    def __init__(self):
        # Load pre-trained face detector
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
    
    def detect_faces(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect all faces in a frame.
        Returns list of face dictionaries with bounding box info.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces_rects = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(50, 50)
        )
        
        faces = []
        h, w = frame.shape[:2]
        
        for (x, y, width, height) in faces_rects:
            center_x = x + width // 2
            center_y = y + height // 2
            
            # Face on left or right half?
            position = "left" if center_x < w // 2 else "right"
            
            faces.append({
                'x': int(x), 'y': int(y),
                'width': int(width), 'height': int(height),
                'center_x': int(center_x), 'center_y': int(center_y),
                'position': position,
            })
        
        return faces
    
    def identify_speaker(self, frame: np.ndarray) -> Optional[str]:
        """
        Determine which speaker is in the frame.
        Returns 'left' or 'right' based on face position.
        """
        faces = self.detect_faces(frame)
        
        if not faces:
            return None
        
        # Get the largest face
        main_face = max(faces, key=lambda f: f['width'] * f['height'])
        return main_face['position']
    
    def get_face_region(self, frame: np.ndarray, padding: float = 0.5) -> Optional[tuple]:
        """
        Get the face region with padding.
        Returns (x1, y1, x2, y2) or None if no face found.
        """
        faces = self.detect_faces(frame)
        
        if not faces:
            return None
        
        # Get the largest face
        face = max(faces, key=lambda f: f['width'] * f['height'])
        
        h, w = frame.shape[:2]
        
        # Add padding
        pad_x = int(face['width'] * padding)
        pad_y = int(face['height'] * padding)
        
        x1 = max(0, face['x'] - pad_x)
        y1 = max(0, face['y'] - pad_y)
        x2 = min(w, face['x'] + face['width'] + pad_x)
        y2 = min(h, face['y'] + face['height'] + pad_y)
        
        return (x1, y1, x2, y2)

def analyze_speaker_segments(video_path: Path, sample_interval: float = 0.5) -> List[Dict]:
    """
    Analyze video to find when speakers change.
    Returns list of {start_time, end_time, speaker} segments.
    """
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * sample_interval)
    
    detector = FaceDetector()
    samples = []
    
    frame_num = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_num % frame_interval == 0:
            speaker = detector.identify_speaker(frame)
            time_sec = frame_num / fps
            samples.append({'time': time_sec, 'speaker': speaker})
        
        frame_num += 1
    
    cap.release()
    
    # Convert samples to segments
    if not samples:
        return []
    
    segments = []
    current = samples[0]['speaker']
    start_time = samples[0]['time']
    
    for i, sample in enumerate(samples[1:], 1):
        if sample['speaker'] != current:
            segments.append({
                'start': start_time,
                'end': samples[i-1]['time'],
                'speaker': current
            })
            current = sample['speaker']
            start_time = sample['time']
    
    # Final segment
    segments.append({
        'start': start_time,
        'end': samples[-1]['time'],
        'speaker': current
    })
    
    return segments

def extract_reference_face(video_path: Path, target_speaker: str, 
                          start_time: float, end_time: float) -> Optional[str]:
    """
    Extract a reference frame for a specific speaker.
    Saves to temp and returns the path.
    """
    import subprocess
    from pathlib import Path
    
    temp_dir = Path(video_path).parent / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Sample frames to find one with the target speaker
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_time * fps))
    
    detector = FaceDetector()
    
    for _ in range(int((end_time - start_time) * fps / 30)):  # Sample every 30 frames
        ret, frame = cap.read()
        if not ret:
            break
        
        speaker = detector.identify_speaker(frame)
        if speaker == target_speaker:
            # Found a frame with target speaker
            output_path = temp_dir / f"ref_face_{target_speaker}.jpg"
            cv2.imwrite(str(output_path), frame)
            cap.release()
            return str(output_path)
    
    cap.release()
    return None

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
        frame = cv2.imread(str(test_path))
        
        if frame is None:
            print(f"Error: Could not load {test_path}")
            sys.exit(1)
        
        detector = FaceDetector()
        faces = detector.detect_faces(frame)
        speaker = detector.identify_speaker(frame)
        
        print(f"Detected {len(faces)} face(s):")
        for i, face in enumerate(faces):
            print(f"  Face {i+1}: position={face['position']}, "
                  f"size={face['width']}x{face['height']}, "
                  f"center=({face['center_x']}, {face['center_y']})")
        
        print(f"\nSpeaker identified as: {speaker}")
