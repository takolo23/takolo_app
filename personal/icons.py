"""Small inline SVG icons; no external font or network dependency."""
from markupsafe import Markup

PATHS = {
    'message': '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 1 1 19 0Z"/><path d="M7 9h10M7 13h7"/>',
    'grid': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/>',
    'upload': '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'out': '<path d="M7 17 17 7M7 7h10v10"/>',
    'payment': '<path d="M17 7 7 17m10 0H7V7"/>',
    'logout': '<path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4m5-13 5 5-5 5m-5-5h14"/>',
    'spark': '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'download': '<path d="M12 3v13m-5-5 5 5 5-5M4 17v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    'left': '<path d="m10 5-7 7 7 7M3 12h18"/>',
    'right': '<path d="m14 5 7 7-7 7M3 12h18"/>',
    'check': '<path d="m5 12 4 4L19 6"/>',
    'file': '<path d="M14 2H5v20h14V7l-5-5Zm0 0v5h5M8 12h8m-8 4h8"/>',
}

def icon(name):
    return Markup('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + PATHS.get(name, '') + '</svg>')
