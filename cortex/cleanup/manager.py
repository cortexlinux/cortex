import shutil
import json
import time
import uuid
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from pathlib import Path

@dataclass
class QuarantineItem:
    """
    Represents an item in the quarantine.
    
    Args:
        id (str): Unique identifier for the item.
        original_path (str): Original path of the file.
        quarantine_path (str): Path to the quarantined file.
        timestamp (float): Time when the item was quarantined.
        size_bytes (int): Size of the item in bytes.
    """
    id: str
    original_path: str
    quarantine_path: str
    timestamp: float
    size_bytes: int

class CleanupManager:
    """
    Manages the quarantine (undo) system for cleaned files.
    """
    def __init__(self):
        self.quarantine_dir = Path.home() / ".cortex" / "trash"
        self.metadata_file = self.quarantine_dir / "metadata.json"
        self._ensure_dir()

    def _ensure_dir(self):
        """Ensure quarantine directory exists with secure permissions."""
        if not self.quarantine_dir.exists():
            self.quarantine_dir.mkdir(parents=True, mode=0o700)

    def _load_metadata(self) -> Dict[str, dict]:
        """Load metadata from JSON file."""
        if not self.metadata_file.exists():
            return {}
        try:
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save_metadata(self, metadata: Dict[str, dict]):
        """Save metadata to JSON file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def quarantine_file(self, filepath_str: str) -> Optional[str]:
        """
        Move a file to quarantine and return its ID.
        
        Args:
            filepath_str (str): Path to the file to quarantine.
            
        Returns:
            Optional[str]: ID of the quarantined item, or None if failed.
        """
        filepath = Path(filepath_str)
        if not filepath.exists():
            return None

        item_id = str(uuid.uuid4())[:8]
        filename = filepath.name
        quarantine_path = self.quarantine_dir / f"{item_id}_{filename}"
        
        try:
            # Get file stats before moving
            size = filepath.stat().st_size
            
            # Check if we have write access to the file
            if not os.access(filepath, os.W_OK):
                return None

            shutil.move(str(filepath), str(quarantine_path))
            
            item = QuarantineItem(
                id=item_id,
                original_path=str(filepath),
                quarantine_path=str(quarantine_path),
                timestamp=time.time(),
                size_bytes=size
            )
            
            metadata = self._load_metadata()
            metadata[item_id] = asdict(item)
            self._save_metadata(metadata)
            
            return item_id
            
        except Exception:
            # Log error?
            return None

    def restore_item(self, item_id: str) -> bool:
        """
        Restore a file from quarantine.
        
        Args:
            item_id (str): ID of the item to restore.
            
        Returns:
            bool: True if restored successfully, False otherwise.
        """
        metadata = self._load_metadata()
        if item_id not in metadata:
            return False
            
        item_data = metadata[item_id]
        original_path = Path(item_data['original_path'])
        quarantine_path = Path(item_data['quarantine_path'])
        
        if not quarantine_path.exists():
            return False
            
        try:
            # Ensure parent dir exists
            if not original_path.parent.exists():
                original_path.parent.mkdir(parents=True)
                
            shutil.move(str(quarantine_path), str(original_path))
            
            del metadata[item_id]
            self._save_metadata(metadata)
            return True
        except Exception:
            return False

    def list_items(self) -> List[QuarantineItem]:
        """
        List all items in quarantine.
        
        Returns:
            List[QuarantineItem]: List of quarantined items sorted by date.
        """
        metadata = self._load_metadata()
        items = []
        for k, v in metadata.items():
            items.append(QuarantineItem(**v))
        return sorted(items, key=lambda x: x.timestamp, reverse=True)

    def cleanup_old_items(self, days: int = 30):
        """
        Remove quarantine items older than X days.
        
        Args:
            days (int): Age in days to expire items.
        """
        metadata = self._load_metadata()
        now = time.time()
        cutoff = now - (days * 86400)
        
        to_remove = []
        for item_id, data in metadata.items():
            if data['timestamp'] < cutoff:
                to_remove.append(item_id)
                
        for item_id in to_remove:
            path = Path(metadata[item_id]['quarantine_path'])
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            del metadata[item_id]
            
        if to_remove:
            self._save_metadata(metadata)
