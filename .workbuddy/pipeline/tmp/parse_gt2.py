"""Extract Google Trends daily trending searches from HTML page"""
import re, json

with open(r'C:\Users\DD\WorkBuddy\2026-06-25-11-10-03\.workbuddy\pipeline\tmp\gt_us.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Look for AF_initDataCallback with actual data
# Pattern: AF_initDataCallback({key: 'ds:N', hash: 'N', data:[...], sideChannel: {}});
pattern = r"AF_initDataCallback\(\{key:\s*'([^']+)',\s*hash:\s*'([^']+)',\s*data:(.+?),\s*sideChannel:\s*\{\}\}\)"
matches = list(re.finditer(pattern, text))
print(f"Found {len(matches)} data callbacks")

for i, m in enumerate(matches):
    key = m.group(1)
    hash_val = m.group(2)
    data_str = m.group(3)
    print(f"\nBlock {i}: key='{key}' hash='{hash_val}' data_len={len(data_str)}")
    if len(data_str) < 500:
        print(f"  data: {data_str[:300]}")
    else:
        print(f"  data starts: {data_str[:200]}...")

# Try another approach: look for embedded trending data
# Sometimes it's in a JSON object with specific structure
# Search for feedEntry or trendHistory
for kw in ['feedEntry', 'trendHistory', 'trendingSearch', 'dailyTrend']:
    count = text.count(kw)
    if count > 0:
        print(f"\n'{kw}': {count} occurrences")
        idx = text.index(kw)
        print(f"  at {idx}: {text[max(0,idx-30):idx+200]}")
