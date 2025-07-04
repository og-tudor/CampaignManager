import json
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from core import (
    logger,
    CAMPAIGN_JSON_PATH,
    SCHEDULE_JSON_PATH,
    VIDEO_CAMPAIGN_DIR,
    VIDEO_FILLER_DIR,
    PLACEHOLDER_IMAGE_PATH,
    campaign_plays_today,
    campaign_plays_hour,
    reset_hourly_counters,
    reset_daily_counters
)


class ScheduleManager:
    def __init__(self):
        self.start_time = None
        self.campaigns = {}
        self.schedule = {}
        self.load_campaigns()
        self.load_schedule()

    
    def load_campaigns(self):
        """Load campaigns from JSON file"""
        try:
            if CAMPAIGN_JSON_PATH.exists():
                with open(CAMPAIGN_JSON_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert campaigns list to dict for easy lookup
                    self.campaigns = {
                        campaign['id']: campaign 
                        for campaign in data.get('campaigns', [])
                    }
                logger.info(f"Loaded {len(self.campaigns)} campaigns")
            else:
                logger.warning("No campaigns.json file found")
                self.campaigns = {}
        except Exception as e:
            logger.error(f"Error loading campaigns: {e}")
            self.campaigns = {}
    
    def load_schedule(self):
        """Load schedule from JSON file"""
        try:
            if SCHEDULE_JSON_PATH.exists():
                with open(SCHEDULE_JSON_PATH, 'r', encoding='utf-8') as f:
                    self.schedule = json.load(f)
                
                logger.info(f"Loaded schedule for {self.schedule.get('date', 'unknown date')} with {len(self.schedule.get('playlist', []))} items")

                if self.schedule.get("relative", False):
                    if not self.start_time:
                        self.start_time = datetime.now()
                        logger.info(f"[RELATIVE-MODE] Start time set to {self.start_time.strftime('%H:%M:%S')}")
                    else:
                        logger.info(f"[RELATIVE-MODE] Using existing start time: {self.start_time.strftime('%H:%M:%S')}")
            else:
                logger.warning("No schedule.json file found")
                self.schedule = {}
        except Exception as e:
            logger.error(f"Error loading schedule: {e}")
            self.schedule = {}

    
    # ScheduleManager  – acceptă și YYYY-MM-DD
    def is_schedule_for_today(self) -> bool:
        # if it's relative, we assume it's always for today
        if self.schedule.get("relative", False):
            return True
        if 'date' not in self.schedule:
            return False
        date_str = self.schedule['date']
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                schedule_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            logger.error("Unrecognised schedule date format")
            return False
        return schedule_date == datetime.now().date()

    
    def get_current_scheduled_item(self) -> Optional[Tuple[dict, dict]]:
        """Get the currently scheduled item based on current time"""
        if not self.is_schedule_for_today():
            logger.info("No valid schedule for today")
            return None
        
        now = datetime.now()
        relative = self.schedule.get("relative", False)
        sorted_playlist = []

        for item in self.schedule.get('playlist', []):
            try:
                offset_time = datetime.strptime(item['at'], "%H:%M:%S")
                duration = item.get("duration", 30)
                if relative:
                    start_dt = self.start_time + timedelta(
                        hours=offset_time.hour,
                        minutes=offset_time.minute,
                        seconds=offset_time.second
                    )
                else:
                    start_dt = datetime.combine(now.date(), offset_time.time())

                end_dt = start_dt + timedelta(seconds=duration)
                sorted_playlist.append((start_dt, end_dt, item))
            except Exception as e:
                logger.warning(f"Invalid time in playlist item {item.get('at')}: {e}")
        
        for start_dt, end_dt, item in sorted_playlist:
            if start_dt <= now < end_dt:
                item_id = item.get('id')
                item_type = item.get('type', 'filler')
                if item_type == 'campaign' and item_id in self.campaigns:
                    logger.info(f"[RELATIVE] Scheduled campaign active: {item_id}")
                    return item, self.campaigns[item_id]
                elif item_type == 'filler':
                    logger.info(f"[RELATIVE] Scheduled filler active: {item_id}")
                    return item, None

        
        return None
    
    def get_next_scheduled_item_time(self) -> Optional[datetime]:
        """Get the time when the next scheduled item starts"""
        if not self.is_schedule_for_today():
            return None
        
        current_time = datetime.now().time()
        playlist = self.schedule.get('playlist', [])
        
        # Find next scheduled item
        next_times = []
        for item in playlist:
            try:
                item_time = datetime.strptime(item['at'], '%H:%M:%S').time()
                if item_time > current_time:
                    next_datetime = datetime.combine(datetime.now().date(), item_time)
                    next_times.append(next_datetime)
            except Exception as e:
                logger.warning(f"Invalid time format in playlist item: {item.get('at')} - {e}")
                continue
        
        if next_times:
            return min(next_times)
        return None
    
    def get_all_playlist_items(self) -> List[dict]:
        """Get all playlist items with enhanced info"""
        if not self.is_schedule_for_today():
            return []
        
        playlist = self.schedule.get('playlist', [])
        enhanced_playlist = []
        now = datetime.now()
        relative = self.schedule.get("relative", False)

        for item in playlist:
            try:
                offset_time = datetime.strptime(item['at'], "%H:%M:%S")
                duration_seconds = item.get('duration', 30)

                if relative:
                    start_datetime = self.start_time + timedelta(
                        hours=offset_time.hour,
                        minutes=offset_time.minute,
                        seconds=offset_time.second
                    )
                else:
                    start_datetime = datetime.combine(now.date(), offset_time.time())

                end_datetime = start_datetime + timedelta(seconds=duration_seconds)
                end_time = end_datetime.time()

                if start_datetime <= now < end_datetime:
                    status = 'current'
                elif now >= end_datetime:
                    status = 'past'
                else:
                    status = 'future'

                # Get name
                item_name = item.get('id', 'Unknown')
                if item.get('type') == 'campaign' and item.get('id') in self.campaigns:
                    campaign = self.campaigns[item.get('id')]
                    item_name = campaign.get('name', item.get('id'))

                enhanced_item = {
                    'id': item.get('id'),
                    'name': item_name,
                    'type': item.get('type', 'filler'),
                    'at': item.get('at'),
                    'duration': duration_seconds,
                    'status': status,
                    'end_time': end_datetime.strftime('%H:%M:%S')
                }

                enhanced_playlist.append(enhanced_item)
            except Exception as e:
                logger.warning(f"Error processing playlist item: {e}")
                continue
        
        # Sort by time
        enhanced_playlist.sort(key=lambda x: x['at'])
        return enhanced_playlist


class VideoService:
    def __init__(self, schedule_manager: ScheduleManager):
        self.schedule_manager = schedule_manager
        self.current_video_path = None
        self.current_video_type = None
        self.last_served_video = None
        self.current_video_index = 0

    def get_next_video(self):
        """Get the next video based on schedule and availability"""
        reset_hourly_counters()
        reset_daily_counters()

        scheduled_result = self.schedule_manager.get_current_scheduled_item()

        if scheduled_result:
            scheduled_item, campaign_info = scheduled_result
            item_type = scheduled_item.get('type', 'filler')
            item_id = scheduled_item.get('id')

            # === CAMPAIGN VIDEO ===
            if item_type == 'campaign' and campaign_info:
                video_file = campaign_info.get('video_file')
                if video_file:
                    video_path = VIDEO_CAMPAIGN_DIR / video_file
                    if video_path.exists():
                        self.current_video_path = video_path
                        self.current_video_type = 'campaign'
                        self.last_served_video = {
                            "path": video_path,
                            "type": 'campaign',
                            "info": campaign_info
                        }

                        campaign_id = campaign_info.get('id')
                        if campaign_id:
                            campaign_plays_hour[campaign_id] = campaign_plays_hour.get(campaign_id, 0) + 1
                            campaign_plays_today[campaign_id] = campaign_plays_today.get(campaign_id, 0) + 1

                        logger.info(f"[SCHEDULED-CAMPAIGN] {self.current_video_path.name}")
                        return self.current_video_path, 'campaign'
                    else:
                        logger.warning(f"[MISSING-CAMPAIGN] Video not found: {video_file} → using placeholder")
                        return self._serve_placeholder(f"Missing campaign video: {video_file}")

            # === FILLER VIDEO ===
            elif item_type == 'filler':
                filler_files = list(VIDEO_FILLER_DIR.glob("*.mp4"))

                for filler_file in filler_files:
                    if filler_file.stem == item_id or filler_file.name == f"{item_id}.mp4":
                        self.current_video_path = filler_file
                        self.current_video_type = 'filler'
                        self.last_served_video = {
                            "path": filler_file,
                            "type": 'filler',
                            "info": {'id': item_id, 'scheduled': True}
                        }
                        logger.info(f"[SCHEDULED-FILLER] {self.current_video_path.name}")
                        return self.current_video_path, 'filler'

                # Filler missing: try any other filler
                if filler_files:
                    filler_file = filler_files[self.current_video_index % len(filler_files)]
                    self.current_video_index = (self.current_video_index + 1) % len(filler_files)
                    self.current_video_path = filler_file
                    self.current_video_type = 'filler'
                    self.last_served_video = {
                        "path": filler_file,
                        "type": 'filler',
                        "info": {'scheduled': False, 'fallback': True, 'message': f"Missing filler: {item_id}.mp4"}
                    }
                    logger.warning(f"[FILLER-FALLBACK] {item_id}.mp4 missing → using {filler_file.name}")
                    return self.current_video_path, 'filler'
                else:
                    logger.warning(f"[NO-FILLERS] Filler '{item_id}' not found and no fillers available → placeholder")
                    return self._serve_placeholder(f"Missing filler and no alternatives: {item_id}.mp4")

        # No scheduled item – fallback
        return self._serve_placeholder("No scheduled content at this time")

    def _serve_placeholder(self, message="No content available"):
        if PLACEHOLDER_IMAGE_PATH.exists():
            self.current_video_type = "placeholder"
            self.last_served_video = {
                "path": PLACEHOLDER_IMAGE_PATH,
                "type": "placeholder",
                "info": {"message": message}
            }
            logger.info(f"[PLACEHOLDER] {message}")
            return PLACEHOLDER_IMAGE_PATH, 'placeholder'
        else:
            logger.error("[FATAL] No placeholder image found")
            return None, 'error'

    def get_current_video_info(self):
        """Get information about the currently served video"""
        # Check if we have a last served video
        if not self.last_served_video or not self.last_served_video.get("path"):
            return None

        file_path = self.last_served_video["path"]
        content_type = self.last_served_video["type"]
        info = self.last_served_video.get("info", {})

        response_data = {
            "id": file_path.stem if hasattr(file_path, 'stem') else str(file_path).split('/')[-1].split('.')[0],
            "type": content_type,
            "filename": file_path.name if hasattr(file_path, 'name') else str(file_path).split('/')[-1],
            "path": str(file_path),
            "scheduled": info.get("scheduled", False),
            "fallback": info.get("fallback", False)
        }

        # Add campaign info if it's a campaign video
        if content_type == "campaign" and info:
            response_data["campaign_name"] = info.get("name", "Unknown Campaign")
            response_data["campaign_id"] = info.get("id", "unknown")
        elif content_type == "placeholder":
            response_data["message"] = info.get("message", "Placeholder content")

        return response_data