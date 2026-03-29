import os
from dotenv import load_dotenv
load_dotenv()
k = os.getenv('OPENAI_API_KEY')
if not k:
    print('NOT SET')
else:
    print('SET')
    print('masked:', k[:6] + '...' + k[-6:])
    print('repr:', repr(k))
    print('len:', len(k))
    print('contains_quote:', '"' in k or "'" in k)
