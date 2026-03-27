from discord import ui
try:
    from discord.ui import Separator, Container, ActionRow, TextDisplay
    print(f"Successfully imported: Separator={Separator}, Container={Container}, ActionRow={ActionRow}, TextDisplay={TextDisplay}")
except ImportError as e:
    print(f"Import failed: {e}")

try:
    print(f"ui.Separator: {getattr(ui, 'Separator', 'Not Found')}")
    print(f"ui.Container: {getattr(ui, 'Container', 'Not Found')}")
except Exception as e:
    print(f"Attr access failed: {e}")
