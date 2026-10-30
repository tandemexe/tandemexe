"""Render real GitHub activity and publish the generated SVGs."""
import base64
import json
import math
import os
import re
from pathlib import Path
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

TOKEN = os.environ['GITHUB_TOKEN']
PROFILE_TOKEN = os.environ.get('PROFILE_TOKEN') or TOKEN
REPOSITORY = os.environ['GITHUB_REPOSITORY']
OWNER = REPOSITORY.split('/')[0]
DIST = Path('dist')
DIST.mkdir(exist_ok=True)

def api(path, method='GET', payload=None, allow_missing=False, profile_read=False):
    request = urllib.request.Request(
        'https://api.github.com'+path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+(PROFILE_TOKEN if profile_read else TOKEN),'Accept':'application/vnd.github+json',
                 'User-Agent':'profile-activity','X-GitHub-Api-Version':'2022-11-28'},
        method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise RuntimeError(f'GitHub returned HTTP {error.code} for {method} {path}') from None

query = '''query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      startedAt
      endedAt
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}'''
response = api('/graphql', 'POST', {'query':query, 'variables':{'login':OWNER}},profile_read=True)
if response.get('errors'):
    raise RuntimeError('GitHub contribution calendar is unavailable.')
collection = response['data']['user']['contributionsCollection']
calendar = collection['contributionCalendar']
start,end = collection['startedAt'][:10],collection['endedAt'][:10]
days = [day for week in calendar['weeks'] for day in week['contributionDays'] if start <= day['date'] <= end]
active = sum(day['contributionCount'] > 0 for day in days)
longest = streak = 0
for day in days:
    streak = streak+1 if day['contributionCount'] else 0
    longest = max(longest, streak)

cards=[]
for x,value,label in [(150,calendar['totalContributions'],'Contributions'),(450,active,'Active days'),(750,longest,'Longest streak')]:
    cards.append(f'<text x="{x}" y="104" text-anchor="middle" font-size="57" font-weight="600" fill="#E7C65F">{value:,}</text>'
                 f'<text x="{x}" y="144" text-anchor="middle" font-size="21" fill="#DDDCD4">{label}</text>')
stats=f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="212" viewBox="0 0 900 212" role="img" aria-label="Real GitHub statistics over the last twelve months">
<title>Real GitHub statistics over the last twelve months</title>
<rect x=".5" y=".5" width="899" height="211" rx="6" fill="#0B0E13" stroke="#343840"/>
<g font-family="Consolas,'Courier New',monospace">{''.join(cards)}</g>
<path d="M300 49v107M600 49v107M24 173h852" stroke="#30343B"/>
<text x="24" y="28" font-family="Consolas,monospace" font-size="13" letter-spacing="1" fill="#95979F">LAST 12 MONTHS</text>
<text x="876" y="28" text-anchor="end" font-family="Consolas,monospace" font-size="13" fill="#95979F">{days[0]['date']} / {days[-1]['date']}</text>
<text x="450" y="196" text-anchor="middle" font-family="Consolas,monospace" font-size="13" fill="#95979F">GitHub contribution calendar / UTC</text></svg>'''
(DIST/'stats.svg').write_text(stats,encoding='utf-8')

recent=days[-90:]
ceiling=max(4,math.ceil(max(day['contributionCount'] for day in recent)/4)*4)
left,right,top,bottom=64,872,45,208
points=[]
for index,day in enumerate(recent):
    x=left+(right-left)*index/max(1,len(recent)-1)
    y=bottom-(bottom-top)*day['contributionCount']/ceiling
    points.append((x,y))
grid=[]
for step in range(5):
    value=ceiling*step//4
    y=bottom-(bottom-top)*step/4
    grid.append(f'<path d="M{left} {y:.1f}H{right}" stroke="#252A32"/><text x="48" y="{y+5:.1f}" text-anchor="end" font-size="14" fill="#92969F">{value}</text>')
for fraction in [0,.25,.5,.75,1]:
    index=round(fraction*(len(recent)-1))
    x=points[index][0]
    date=recent[index]['date'][5:]
    grid.append(f'<text x="{x:.1f}" y="239" text-anchor="middle" font-size="14" fill="#92969F">{date}</text>')
line=' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
area=f'{left},{bottom} '+line+f' {right},{bottom}'
chart=f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="260" viewBox="0 0 900 260" role="img" aria-label="Daily GitHub contributions over the last ninety days">
<title>Daily GitHub contributions over the last ninety days</title>
<defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#E7C65F" stop-opacity=".2"/><stop offset="1" stop-color="#E7C65F" stop-opacity="0"/></linearGradient></defs>
<rect x=".5" y=".5" width="899" height="259" rx="6" fill="#0B0E13" stroke="#343840"/>
<g font-family="Consolas,monospace"><text x="24" y="26" font-size="13" letter-spacing="1" fill="#B5B6B9">DAILY CONTRIBUTIONS / LAST 90 DAYS</text>{''.join(grid)}</g>
<polygon points="{area}" fill="url(#area)"/><polyline points="{line}" stroke="#E7C65F" stroke-width="2.5" stroke-linejoin="round" fill="none"/>
</svg>'''
(DIST/'activity-chart.svg').write_text(chart,encoding='utf-8')

snake_path = DIST/'contribution-snake.svg'
snake = snake_path.read_text(encoding='utf-8')
root = ET.fromstring(snake)
# Keep dimensions and colors explicit for SVG renderers without CSS variables
# or CSS geometry properties. Browser keyframe animation remains intact.
colors = dict(re.findall(r'(--[a-z0-9]+):([^;}]+)', snake))
colors.update({'--cb':'#353336','--cs':'#E7C65F','--ce':'#1B1D22','--c0':'#1B1D22','--c1':'#49412B','--c2':'#7B6836','--c3':'#AF9446','--c4':'#E7C65F'})
for variable,value in colors.items():
    snake = snake.replace('var('+variable+')',value)
snake = re.sub(r'<rect class="(c(?: c[0-9]+)?)"',r'<rect width="12" height="12" class="\1"',snake)
if 'profile-background' not in snake:
    position = snake.index('>',snake.index('<svg'))+1
    bounds = root.attrib.get('viewBox', '').split()
    x,y,width,height = bounds if len(bounds) == 4 else ('0','0','100%','100%')
    background = f'<rect id="profile-background" x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="#0B0E13"/>'
    snake = snake[:position]+background+snake[position:]
snake_path.write_text(snake,encoding='utf-8')

if os.environ.get('PROFILE_PREVIEW_ONLY') == '1':
    print('Activity preview generated.')
    raise SystemExit(0)

base = '/repos/'+REPOSITORY
ref = api(base+'/git/ref/heads/output', allow_missing=True)
parent = api(base+'/git/commits/'+ref['object']['sha']) if ref else None
tree_items = []
for path in [DIST/'stats.svg',DIST/'activity-chart.svg',snake_path]:
    blob = api(base+'/git/blobs','POST',{'content':base64.b64encode(path.read_bytes()).decode(),'encoding':'base64'})
    tree_items.append({'path':path.name,'mode':'100644','type':'blob','sha':blob['sha']})
tree = api(base+'/git/trees','POST',{'tree':tree_items})
if parent and parent['tree']['sha'] == tree['sha']:
    print('Activity is current; no commit needed.')
else:
    commit = api(base+'/git/commits','POST',{
        'message':'Refresh contribution activity', 'tree':tree['sha'],
        'parents':[parent['sha']] if parent else [],
        'author':{'name':'github-actions[bot]','email':'41898282+github-actions[bot]@users.noreply.github.com'}})
    if ref:
        api(base+'/git/refs/heads/output','PATCH',{'sha':commit['sha'],'force':False})
    else:
        api(base+'/git/refs','POST',{'ref':'refs/heads/output','sha':commit['sha']})
    print('Published activity:',commit['sha'])
