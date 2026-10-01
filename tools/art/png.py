"""Bounded 8-bit non-interlaced PNG reader and deterministic RGBA writer.

Deliberately small adapter format, not a general imaging library. No quantization,
resampling, cleanup, art generation or hidden third-party image dependency.
"""
from __future__ import annotations
import struct
import zlib
from .manifest import ArtError, require

SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PIXELS = 4_194_304


def encode(width: int, height: int, rgba: bytes) -> bytes:
    require(width > 0 and height > 0 and width * height <= MAX_PIXELS and len(rgba) == width * height * 4, 'invalid RGBA dimensions')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    raw = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    # Fixed uncompressed DEFLATE blocks make bytes independent of zlib compression versions.
    compressed = bytearray(b'\x78\x01')
    for start in range(0, len(raw), 65535):
        block = raw[start:start + 65535]
        compressed += bytes([int(start + len(block) == len(raw))])
        compressed += struct.pack('<HH', len(block), 65535 - len(block)) + block
    compressed += struct.pack('>I', zlib.adler32(raw))
    return SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', bytes(compressed)) + chunk(b'IEND', b'')


def decode(data: bytes) -> tuple[int, int, bytes]:
    require(len(data) <= 64 * 1024 * 1024 and data.startswith(SIGNATURE), 'invalid or oversized PNG')
    pos, chunks, payload, palette, alpha = 8, [], bytearray(), b'', b''
    width = height = channels = color = 0
    while pos < len(data):
        require(pos + 12 <= len(data), 'truncated PNG chunk')
        size = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + size + 12
        require(end <= len(data), 'truncated PNG chunk data')
        body = data[pos + 8:end - 4]
        require(zlib.crc32(kind + body) == struct.unpack('>I', data[end - 4:end])[0], 'PNG CRC mismatch')
        require(chunks or kind == b'IHDR', 'PNG must begin with IHDR')
        if kind == b'IHDR':
            require(not chunks and size == 13, 'invalid/duplicate PNG header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            require(width > 0 and height > 0 and width * height <= MAX_PIXELS, 'PNG pixel limit exceeded')
            require(depth == 8 and color in (2, 3, 6) and (compression, filtering, interlace) == (0, 0, 0),
                    'PNG adapter requires 8-bit RGB, RGBA or indexed non-interlaced input; export without resampling')
            channels = {2: 3, 3: 1, 6: 4}[color]
        elif kind == b'PLTE':
            require(not palette and not payload and 0 < size <= 768 and size % 3 == 0, 'invalid PNG palette')
            palette = body
        elif kind == b'tRNS':
            require(color == 3 and palette and not alpha and not payload and 0 < size <= len(palette) // 3,
                    'PNG adapter supports tRNS only for indexed PNG; convert RGB+tRNS to RGBA')
            alpha = body
        elif kind == b'IDAT':
            require(not payload or chunks[-1] == b'IDAT', 'noncontiguous PNG image data')
            payload += body
        elif kind == b'IEND':
            require(size == 0 and payload and end == len(data), 'invalid PNG ending')
        else:
            require(kind[0] & 32, f'unsupported critical PNG chunk {kind!r}')
            require(kind not in (b'acTL', b'fcTL', b'fdAT'), 'animated PNG is not a sprite sheet')
        chunks.append(kind)
        pos = end
    require(chunks[-1:] == [b'IEND'] and payload, 'missing PNG image or ending')
    require(color != 3 or palette, 'indexed PNG missing palette')
    row_bytes = width * channels
    expected = (row_bytes + 1) * height
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(payload, expected + 1)
        require(len(raw) == expected and decoder.eof and not decoder.unused_data, 'invalid PNG decompressed size')
    except zlib.error as error:
        raise ArtError('invalid PNG compression') from error
    result = bytearray()
    previous = bytearray(row_bytes)
    for y in range(height):
        start = y * (row_bytes + 1)
        method = raw[start]
        require(method <= 4, 'invalid PNG filter')
        row = bytearray(raw[start + 1:start + 1 + row_bytes])
        for i in range(row_bytes):
            a, b, c = row[i - channels] if i >= channels else 0, previous[i], previous[i - channels] if i >= channels else 0
            if method == 1: predict = a
            elif method == 2: predict = b
            elif method == 3: predict = (a + b) // 2
            elif method == 4:
                p = a + b - c
                distances = (abs(p - a), abs(p - b), abs(p - c))
                predict = (a, b, c)[distances.index(min(distances))]
            else: predict = 0
            row[i] = (row[i] + predict) & 255
        previous = row
        for i in range(0, row_bytes, channels):
            if color == 3:
                index = row[i]
                require(index * 3 < len(palette), 'PNG palette index out of range')
                pixel = palette[index * 3:index * 3 + 3] + bytes([alpha[index] if index < len(alpha) else 255])
            elif color == 2: pixel = row[i:i + 3] + b'\xff'
            else: pixel = row[i:i + 4]
            result += pixel if pixel[3] else b'\0\0\0\0'
    return width, height, bytes(result)
