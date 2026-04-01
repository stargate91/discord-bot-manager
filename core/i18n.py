import os
import json
import re
from core.logger import log

# This class helps us show the bot in different languages (like Hungarian or English)
class LocalizationService:
    def __init__(self, default_lang="hu"):
        self.default_lang = default_lang
        self.current_lang = default_lang
        self.translations = {}
        # We load the default language when we start
        log.info(f"[DEBUG] LocalizationService: Initializing for {default_lang}")
        self.load_translations(default_lang)
        log.info(f"[DEBUG] LocalizationService: Initialization for {default_lang} complete.")

    def load_translations(self, lang):
        """This function loads the right language file (locales/hu.json or locales/en.json)."""
        self.current_lang = lang
        
        # Absolute path resolution logic
        try:
            # We get the directory of the current file (core/) and go up one level to the root
            current_file_path = os.path.abspath(__file__)
            core_dir = os.path.dirname(current_file_path)
            base_dir = os.path.dirname(core_dir)
            
            locales_dir = os.path.join(base_dir, "locales")
            file_path = os.path.normpath(os.path.join(locales_dir, f"{lang}.json"))
            
            log.info(f"[Localization] Initializing {lang} from: {file_path}")
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        new_data = json.load(f)
                        self.translations.clear()
                        self.translations.update(new_data)
                    log.info(f"[Localization] Successfully loaded {len(self.translations)} keys from {file_path}")
                except Exception as e:
                    log.error(f"[Localization] Error reading {file_path}: {e}")
                    # Backup to hu if en fails, but avoid infinite recursion
                    if lang != "hu":
                        self.load_translations("hu")
            else:
                log.warning(f"[Localization] File NOT FOUND at: {file_path}")
                # Try fallback to root for legacy support or alternative structures
                root_fallback = os.path.join(base_dir, f"{lang}.json")
                if os.path.exists(root_fallback):
                    log.info(f"[Localization] Found fallback in root: {root_fallback}")
                    with open(root_fallback, "r", encoding="utf-8") as f:
                        self.translations.clear()
                        self.translations.update(json.load(f))
                elif lang != "hu":
                    self.load_translations("hu")
                    
        except Exception as e:
            log.error(f"[Localization] Fatal error in load_translations: {e}")

    def get(self, key, default=None, **kwargs):
        """This function gets a translated text and fills in any variables/icons."""
        # 1. Look for the 'key' in our dictionary
        text = self.translations.get(key, default or key)
        
        if not isinstance(text, str):
            text = str(text)

        # 2. Support Icon placeholders like {SUCCESS} or {ERROR}
        if "{" in text:
            try:
                from core.icons import Icons
                placeholders = re.findall(r"\{([A-Z0-9_]+)\}", text)
                for p in placeholders:
                    if hasattr(Icons, p):
                        icon_val = getattr(Icons, p)
                        text = text.replace(f"{{{p}}}", str(icon_val))
            except Exception as e:
                log.error(f"[Localization] Icon replacement failed for '{key}': {e}")

        # 3. Support for dynamic variables (.format(**kwargs))
        try:
            return text.format(**kwargs)
        except Exception as e:
            # If we messed up the formatting, just return the plain text
            log.error(f"Error formatting translation key '{key}': {e}")
            return text

    def localize_commands(self, tree, guild=None):
        """This function translates only the descriptions of our slash commands."""
        try:
            commands = tree.get_commands(guild=guild)
            for cmd in commands:
                # We look for a description key like 'desc_status'
                key = f"desc_{cmd.name.replace('-', '_')}"
                if key in self.translations:
                    cmd.description = self.translations[key]
                
                # Note: Parameter descriptions are read-only in discord.py, 
                # so we skip them here or use a Translator class for those.
        except Exception as e:
            log.error(f"Error during command localization: {e}")
