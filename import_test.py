from dotenv import load_dotenv, find_dotenv
import os

load_dotenv(find_dotenv())

k = os.getenv('OPENAI_API_KEY')
print('OPENAI_API_KEY set:', bool(k))
if k:
    print('masked:', k[:6] + '...' + k[-6:])

try:
    import utils
    print('Imported utils from:', getattr(utils, '__file__', 'unknown'))
except Exception as e:
    print('utils import failed:', repr(e))
