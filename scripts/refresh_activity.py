"""Render real GitHub activity and publish the generated SVGs."""
import base64
import json
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

cards = []
for x,value,label in [(40,calendar['totalContributions'],'CONTRIBUTIONS'),(440,active,'ACTIVE DAYS'),(840,longest,'LONGEST STREAK')]:
    cards.append(f'<text x="{x}" y="83" font-size="54" font-weight="700" fill="#FFD600">{value:,}</text>'
                 f'<text x="{x}" y="118" font-family="Consolas,monospace" font-size="12" letter-spacing="2" fill="#A58B19">{label}</text>')
stats = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="174" viewBox="0 0 1200 174" role="img" aria-label="GitHub contribution statistics over the last twelve months">
<title>GitHub contribution statistics over the last twelve months</title>
<rect width="1200" height="174" rx="16" fill="#090909"/>
<g font-family="Arial,Helvetica,sans-serif">{''.join(cards)}</g>
<path d="M400 34v88M800 34v88" stroke="#3B330F"/>
<text x="40" y="153" font-family="Consolas,monospace" font-size="10" letter-spacing="1" fill="#A58B19">LAST 12 MONTHS</text>
<text x="1160" y="153" text-anchor="end" font-family="Consolas,monospace" font-size="10" letter-spacing="1" fill="#A58B19">{days[0]['date']} / {days[-1]['date']}</text></svg>'''
(DIST/'stats.svg').write_text(stats,encoding='utf-8')

snake_path = DIST/'contribution-snake.svg'
snake = snake_path.read_text(encoding='utf-8')
root = ET.fromstring(snake)
# Keep dimensions and colors explicit for SVG renderers without CSS variables
# or CSS geometry properties. Browser keyframe animation remains intact.
colors = dict(re.findall(r'(--[a-z0-9]+):([^;}]+)', snake))
colors['--cb'] = '#302A10'
for variable,value in colors.items():
    snake = snake.replace('var('+variable+')',value)
snake = re.sub(r'<rect class="(c(?: c[0-9]+)?)"',r'<rect width="12" height="12" class="\1"',snake)
if 'profile-background' not in snake:
    position = snake.index('>',snake.index('<svg'))+1
    bounds = root.attrib.get('viewBox', '').split()
    x,y,width,height = bounds if len(bounds) == 4 else ('0','0','100%','100%')
    background = f'<rect id="profile-background" x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#090909"/>'
    snake = snake[:position]+background+snake[position:]
snake_path.write_text(snake,encoding='utf-8')

if os.environ.get('PROFILE_PREVIEW_ONLY') == '1':
    print('Activity preview generated.')
    raise SystemExit(0)

base = '/repos/'+REPOSITORY
ref = api(base+'/git/ref/heads/output', allow_missing=True)
parent = api(base+'/git/commits/'+ref['object']['sha']) if ref else None
tree_items = []
for path in [DIST/'stats.svg',snake_path]:
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
