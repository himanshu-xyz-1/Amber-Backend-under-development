import os
import logging

logger = logging.getLogger(__name__)

KILL_SWITCH_FILE = "/tmp/amber_kill_switch.lock"

class KillSwitchManager:
    """
    Manages the emergency Kill-Switch.
    Uses an ephemeral lock file to ensure ultra-low latency (< 1ms) cross-worker sync
    without requiring Redis or DB queries on every tool execution.
    """
    @property
    def is_engaged(self) -> bool:
        return os.path.exists(KILL_SWITCH_FILE)

    def engage(self) -> None:
        try:
            with open(KILL_SWITCH_FILE, "w") as f:
                f.write("ENGAGED")
            logger.warning("🚨 EMERGENCY KILL-SWITCH ENGAGED! System downgraded to Read-Only.")
        except Exception as e:
            logger.error(f"Failed to engage kill switch: {e}")

    def disengage(self) -> None:
        try:
            if os.path.exists(KILL_SWITCH_FILE):
                os.remove(KILL_SWITCH_FILE)
            logger.info("✅ Emergency kill-switch disengaged. Normal operations resumed.")
        except Exception as e:
            logger.error(f"Failed to disengage kill switch: {e}")

kill_switch = KillSwitchManager()
