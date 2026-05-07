import asyncio
import httpx
import sys

BASE_URL = 'http://127.0.0.1:8080'

sys.path.insert(0, '.')
from app.core.security import create_access_token

admin_token = create_access_token('af301f02-d269-45cf-8045-d454ba22c412', 'admin')
headers = {'Authorization': f'Bearer {admin_token}', 'X-API-Version': '1'}

async def test_endpoints():
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as client:
        print('1. Testing GET /api/profiles (List/Filter)')
        r1 = await client.get('/api/profiles?country_id=NG&limit=2')
        print(f'Status: {r1.status_code}')
        if r1.status_code == 200:
            d = r1.json()
            print(f"Total: {d.get('total')}, Profiles returned: {len(d.get('data', []))}")
        else:
            print(r1.text)

        print('\n2. Testing GET /api/profiles/search (NL Search)')
        r2 = await client.get('/api/profiles/search?q=young+females+from+nigeria&limit=2')
        print(f'Status: {r2.status_code}')
        if r2.status_code == 200:
            d = r2.json()
            print(f"Total: {d.get('total')}, Profiles returned: {len(d.get('data', []))}")
        else:
            print(r2.text)

        print('\n3. Testing POST /api/profiles (Create)')
        r3 = await client.post('/api/profiles', json={'name': 'Test User For Endpoints', 'gender': 'female', 'age': 25, 'country_id': 'NG'})
        print(f'Status: {r3.status_code}')
        profile_id = None
        if r3.status_code in (200, 201):
            d = r3.json()
            profile_id = d.get('data', {}).get('id')
            print(f'Created profile ID: {profile_id}')
        else:
            print(r3.text)

        if profile_id:
            print('\n4. Testing DELETE /api/profiles/{id} (Delete)')
            r4 = await client.delete(f'/api/profiles/{profile_id}')
            print(f'Status: {r4.status_code}')
            if r4.status_code != 200:
                print(r4.text)

asyncio.run(test_endpoints())
