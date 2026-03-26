import os
import json
from core.logger import log

class LocalizationService:
    def __init__(self, default_lang="hu"):
        self.default_lang = default_lang
        self.current_lang = default_lang
        self.translations = {}
        self.load_translations(default_lang)

    def load_translations(self, lang):
        """Loads translations from messages_{lang}.json or messages.json for 'hu'."""
        self.current_lang = lang
        file_name = "messages.json" if lang == "hu" else f"messages_{lang}.json"
        
        if os.path.exists(file_name):
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                    self.translations.clear()
                    self.translations.update(new_data)
                log.info(f"Loaded {len(self.translations)} translation keys for language: {lang}")
            except Exception as e:
                log.error(f"Failed to load translations for {lang}: {e}")
                if lang != "hu":
                    self.load_translations("hu") # Fallback
        else:
            log.warning(f"Translation file {file_name} not found. Falling back to default.")
            if lang != "hu":
                self.load_translations("hu")

    def get(self, key, default=None, **kwargs):
        """Returns the translated string for the given key, formatted with kwargs."""
        text = self.translations.get(key, default or key)
        try:
            return str(text).format(**kwargs)
        except Exception as e:
            log.error(f"Error formatting translation key '{key}': {e}")
            return str(text)

    def localize_commands(self, tree, messages, guild=None):
        """Patches command descriptions in the command tree."""
        commands = tree.get_commands(guild=guild)
        for cmd in commands:
            # Update command description
            key = f"desc_{cmd.name.replace('-', '_')}"
            if key in self.translations:
                cmd.description = self.translations[key]
            
            # Update parameter descriptions
            if hasattr(cmd, '_params'):
                for param_name, param in cmd._params.items():
                    param_key = f"desc_param_{param_name.replace('-', '_')}"
                    if param_key in self.translations:
                        param.description = self.translations[param_key]
