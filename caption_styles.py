# Caption Style Presets

CAPTION_STYLES = {
    "normal": {
        "name": "Normal",
        "template": "{title}",
        "description": "Simple title only"
    },
    
    "elegant": {
        "name": "Elegant",
        "template": "✨ {title} ✨",
        "description": "Elegant with sparkles"
    },
    
    "minimal": {
        "name": "Minimal",
        "template": "▸ {title}",
        "description": "Clean minimal style"
    },
    
    "boxed": {
        "name": "Boxed",
        "template": "┏━━━━━━━━━━━━┓\n┃ {title}\n┗━━━━━━━━━━━━┛",
        "description": "Boxed style"
    },
    
    "pro": {
        "name": "Professional",
        "template": "📚 {title}\n━━━━━━━━━━━━━━━",
        "description": "Professional look"
    },
    
    "modern": {
        "name": "Modern",
        "template": "⚡ {title} ⚡\n\n💎 Premium Content",
        "description": "Modern premium style"
    },
    
    "classic": {
        "name": "Classic",
        "template": "📖 {title}\n\n🎓 Educational Content",
        "description": "Classic educational"
    },
    
    "bold": {
        "name": "Bold",
        "template": "🔥 {title} 🔥\n\n🚀 Top Quality",
        "description": "Bold and eye-catching"
    },
    
    "premium": {
        "name": "Premium",
        "template": "💫 {title}\n\n✨ Premium Edition\n━━━━━━━━━━━━",
        "description": "Premium luxury style"
    },
    
    "tech": {
        "name": "Tech",
        "template": "⚙️ {title}\n\n🔧 Technical Content",
        "description": "Tech focused"
    }
}

def apply_caption_style(title: str, style: str = "normal", custom_caption: str = "") -> str:
    """Apply caption style to title"""
    style_config = CAPTION_STYLES.get(style, CAPTION_STYLES["normal"])
    caption = style_config["template"].format(title=title)
    
    if custom_caption:
        caption += f"\n\n{custom_caption}"
    
    return caption

def get_style_list() -> str:
    """Get formatted list of available styles"""
    text = "📋 **CAPTION STYLES**\n\n"
    
    for idx, (key, style) in enumerate(CAPTION_STYLES.items(), 1):
        text += f"{idx}. **{style['name']}**\n"
        text += f"   {style['description']}\n\n"
    
    return text
