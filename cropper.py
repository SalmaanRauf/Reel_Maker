"""
Smart Cropper - Active speaker detection and dynamic 9:16 cropping
Uses YOLOv8 for person detection and implements smooth tracking.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from collections import deque
import subprocess
import json
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

console = Console()


@dataclass
class BoundingBox:
    """Bounding box for a detected person"""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    
    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2
    
    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclass
class CropRegion:
    """Defines a crop region for a frame"""
    x: int  # Top-left x
    y: int  # Top-left y
    width: int
    height: int


class SpeakerTracker:
    """
    Tracks the active speaker/person and provides smooth crop coordinates.
    Uses a sliding window for temporal smoothing to avoid jittery crops.
    """
    
    def __init__(
        self,
        source_width: int,
        source_height: int,
        target_width: int = 1080,
        target_height: int = 1920,
        smoothing_window: int = 15,
        padding: float = 0.15
    ):
        self.source_width = source_width
        self.source_height = source_height
        self.target_width = target_width
        self.target_height = target_height
        self.smoothing_window = smoothing_window
        self.padding = padding
        
        # Calculate crop dimensions to maintain 9:16 from source
        self.target_aspect = target_width / target_height  # 0.5625
        source_aspect = source_width / source_height
        
        if source_aspect > self.target_aspect:
            # Source is wider than target - crop width
            self.crop_height = source_height
            self.crop_width = int(source_height * self.target_aspect)
        else:
            # Source is taller - crop height
            self.crop_width = source_width
            self.crop_height = int(source_width / self.target_aspect)
        
        # History for smoothing
        self.center_history: deque = deque(maxlen=smoothing_window)
        
        # Default to center
        self.last_center_x = source_width / 2
        
    def update(self, detections: List[BoundingBox]) -> CropRegion:
        """
        Update tracker with new detections and return smooth crop region.
        
        Args:
            detections: List of person bounding boxes
            
        Returns:
            CropRegion for this frame
        """
        if not detections:
            # No detections - use last known position
            center_x = self.last_center_x
        else:
            # Find the "main" person (largest/most central)
            main_person = self._select_main_person(detections)
            center_x = main_person.center_x
        
        # Add to history
        self.center_history.append(center_x)
        
        # Smooth using exponential moving average
        smoothed_x = self._smooth_center()
        self.last_center_x = smoothed_x
        
        # Calculate crop region
        crop_x = int(smoothed_x - self.crop_width / 2)
        crop_y = int((self.source_height - self.crop_height) / 2)  # Center vertically
        
        # Clamp to valid range
        crop_x = max(0, min(crop_x, self.source_width - self.crop_width))
        crop_y = max(0, min(crop_y, self.source_height - self.crop_height))
        
        return CropRegion(
            x=crop_x,
            y=crop_y,
            width=self.crop_width,
            height=self.crop_height
        )
    
    def _select_main_person(self, detections: List[BoundingBox]) -> BoundingBox:
        """Select the main person to focus on (largest bounding box)"""
        # Simple heuristic: largest person is likely the speaker
        return max(detections, key=lambda d: d.width * d.height)
    
    def _smooth_center(self) -> float:
        """Apply temporal smoothing to center position"""
        if len(self.center_history) == 0:
            return self.source_width / 2
        
        # Exponential moving average
        weights = np.exp(np.linspace(-1, 0, len(self.center_history)))
        weights /= weights.sum()
        
        return np.average(list(self.center_history), weights=weights)


class PersonDetector:
    """Detects people in video frames using YOLOv8"""
    
    def __init__(self, model_name: str = "yolov8n.pt"):
        if not HAS_YOLO:
            raise ImportError("ultralytics not installed. Run: pip install ultralytics")
        
        console.print(f"[cyan]Loading YOLO model: {model_name}[/cyan]")
        self.model = YOLO(model_name)
        self.person_class_id = 0  # COCO class 0 is 'person'
        
    def detect(self, frame: np.ndarray, confidence_threshold: float = 0.5) -> List[BoundingBox]:
        """
        Detect people in a frame.
        
        Args:
            frame: BGR image as numpy array
            confidence_threshold: Minimum confidence score
            
        Returns:
            List of BoundingBox for detected people
        """
        results = self.model(frame, verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                if int(box.cls) == self.person_class_id and float(box.conf) >= confidence_threshold:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append(BoundingBox(
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        confidence=float(box.conf)
                    ))
        
        return detections


def generate_crop_trajectory(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_width: int = 1080,
    output_height: int = 1920,
    sample_rate: int = 5  # Process every Nth frame for speed
) -> List[Dict]:
    """
    Analyze video segment and generate crop trajectory.
    
    Args:
        video_path: Path to source video
        start_time: Start time in seconds
        end_time: End time in seconds
        output_width: Target width (9:16)
        output_height: Target height (9:16)
        sample_rate: Process every Nth frame
        
    Returns:
        List of crop coordinates per frame
    """
    console.print(f"[cyan]Analyzing video for smart cropping ({start_time:.1f}s - {end_time:.1f}s)...[/cyan]")
    
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Initialize detector and tracker
    detector = PersonDetector()
    tracker = SpeakerTracker(
        source_width=source_width,
        source_height=source_height,
        target_width=output_width,
        target_height=output_height
    )
    
    # Seek to start
    start_frame = int(start_time * fps)
    end_frame = int(end_time * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    crop_data = []
    total_frames = end_frame - start_frame
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Detecting speakers", total=total_frames)
        
        frame_idx = 0
        last_crop = None
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame_idx >= total_frames:
                break
            
            current_frame = start_frame + frame_idx
            
            # Only process every Nth frame for speed
            if frame_idx % sample_rate == 0:
                detections = detector.detect(frame)
                crop_region = tracker.update(detections)
                last_crop = crop_region
            else:
                # Use interpolated/last crop for non-processed frames
                crop_region = last_crop or tracker.update([])
            
            crop_data.append({
                "frame": current_frame,
                "time": current_frame / fps,
                "x": crop_region.x,
                "y": crop_region.y,
                "width": crop_region.width,
                "height": crop_region.height
            })
            
            frame_idx += 1
            progress.update(task, advance=1)
    
    cap.release()
    
    console.print(f"[green]✓ Generated crop trajectory for {len(crop_data)} frames[/green]")
    
    return crop_data


def apply_smart_crop(
    video_path: Path,
    output_path: Path,
    start_time: float,
    end_time: float,
    crop_trajectory: Optional[List[Dict]] = None,
    output_width: int = 1080,
    output_height: int = 1920
) -> Path:
    """
    Apply smart crop to video segment using FFmpeg.
    
    For simplicity, we use a single averaged crop position.
    For more dynamic tracking, crop_trajectory would be used frame-by-frame.
    """
    console.print(f"[cyan]Applying smart crop to create vertical video...[/cyan]")
    
    if crop_trajectory:
        # Average the crop positions for a stable crop
        avg_x = int(np.mean([c["x"] for c in crop_trajectory]))
        avg_y = int(np.mean([c["y"] for c in crop_trajectory]))
        crop_w = crop_trajectory[0]["width"]
        crop_h = crop_trajectory[0]["height"]
    else:
        # Fallback to center crop
        cap = cv2.VideoCapture(str(video_path))
        source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        
        target_aspect = output_width / output_height
        crop_h = source_height
        crop_w = int(source_height * target_aspect)
        avg_x = (source_width - crop_w) // 2
        avg_y = 0
    
    # Build FFmpeg command
    duration = end_time - start_time
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", f"crop={crop_w}:{crop_h}:{avg_x}:{avg_y},scale={output_width}:{output_height}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]FFmpeg error: {result.stderr}[/red]")
        raise RuntimeError("Failed to crop video")
    
    console.print(f"[green]✓ Cropped video saved to {output_path.name}[/green]")
    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 3:
        video = Path(sys.argv[1])
        start = float(sys.argv[2])
        end = float(sys.argv[3])
        
        trajectory = generate_crop_trajectory(video, start, end)
        output = Path(f"./temp/cropped_{start:.0f}_{end:.0f}.mp4")
        apply_smart_crop(video, output, start, end, trajectory)
