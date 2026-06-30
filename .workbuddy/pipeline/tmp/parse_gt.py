"""Extract Google Trends data from saved HTML"""
import re, json

with open(r'C:\Users\DD\WorkBuddy\2026-06-25-11-10-03\.workbuddy\pipeline\tmp\gt_us.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Find all AF_initDataCallback blocks
blocks = re.findall(r'AF_initDataCallback\(({[^}]+})\);', text)
print(f"Found {len(blocks)} AF_initDataCallback blocks")

for i, block in enumerate(blocks):
    # Extract key
    key_m = re.search(r'key:\s*"([^"]+)"', block)
    key = key_m.group(1) if key_m else 'unknown'
    print(f"\n  Block {i}: key={key}")

# Look for embedded trending data in any script
scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
print(f"\nTotal scripts: {len(scripts)}")

# Check for trending search keywords in raw text
for kw in ['trendingSearches', 'dailyTrends', 'scheduledDate']:
    count = text.count(kw)
    print(f"  '{kw}': {count} occurrences")
