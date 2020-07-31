import re, os, sys
from asyncio import ensure_future, gather, get_event_loop, sleep
from collections import deque
from statistics import mean
from time import time, asctime
from aiohttp import ClientSession

MIN_DURATION = 20
MAX_DURATION = 30
STABILITY_DELTA = 2
MIN_STABLE_MEASUREMENTS = 20

total = 0
done = 0
sessions = []


async def run():
    print('fast.com cli')
    ip = await get_ip()
    token = await get_token()
    urls = await get_urls(token)
    conns = await warmup(urls)
    future = ensure_future(measure(conns))
    result = await progress(future)
    await cleanup()
    return result, ip, urls

async def get_ip():
    async with ClientSession() as s:
        resp = await s.get('https://httpbin.org/ip')
        data = await resp.json()
        return data['origin']

async def get_token():
    async with ClientSession() as s:
        resp = await s.get('https://fast.com/')
        text = await resp.text()
        script = re.search(r'<script src="(.*?)">', text).group(1)

        resp = await s.get(f'https://fast.com{script}')
        text = await resp.text()
        token = re.search(r'token:"(.*?)"', text).group(1)
    dot()
    return token


async def get_urls(token):
    async with ClientSession() as s:
        params = {'https': 'true', 'token': token, 'urlCount': 5}
        resp = await s.get('https://api.fast.com/netflix/speedtest', params=params)
        data = await resp.json()
    dot()
    return [x['url'] for x in data]


async def warmup(urls):
    conns = [get_connection(url) for url in urls]
    return await gather(*conns)


async def get_connection(url):
    s = ClientSession()
    sessions.append(s)
    conn = await s.get(url)
    dot()
    return conn


async def measure(conns):
    workers = [measure_speed(conn) for conn in conns]
    await gather(*workers)


async def measure_speed(conn):
    global total, done
    chunk_size = 64 * 2**10
    async for chunk in conn.content.iter_chunked(chunk_size):
        total += len(chunk)
    done += 1


def stabilized(deltas, elapsed):
    return (
        elapsed > MIN_DURATION and
        len(deltas) > MIN_STABLE_MEASUREMENTS and
        max(deltas) < STABILITY_DELTA
    )


async def progress(future):
    start = time()
    measurements = deque(maxlen=10)
    deltas = deque(maxlen=10)

    while True:
        await sleep(0.2)
        elapsed = time() - start
        speed = total / elapsed / 2**17
        measurements.append(speed)

        print(f'\033[2K\r{speed:.3f} mbps', end='', flush=True)

        if len(measurements) == 10:
            delta = abs(speed - mean(measurements)) / speed * 100
            deltas.append(delta)

        if done or elapsed > MAX_DURATION or stabilized(deltas, elapsed):
            future.cancel()
            return speed


async def cleanup():
    await gather(*[s.close() for s in sessions])
    print()


def dot():
    print('.', end='', flush=True)


def main():
    loop = get_event_loop()
    result, ip, urls = loop.run_until_complete(run())
    if sys.platform in ['darwin', 'linux']:
        fname = os.path.join(os.environ['HOME'], 'results.csv')
    elif sys.platform == 'win32':
        fname = os.path.join('\\', 'Downloads', 'results.csv')
    else:
        exit(-1)
    with open(fname, 'a') as f:
        f.write("{},{},{},{}\n".format(asctime(), result, ip, urls))
    return result


if __name__ == '__main__':
    main()
