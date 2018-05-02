# -*- coding: utf-8 -*-
"""
__author__ = 'CodeFace'
"""
import hashlib
import base64
import hmac
import os
import json
import ecdsa
import pyaes
from eth_abi import encode_abi
from eth_utils import function_signature_to_4byte_selector, function_abi_to_4byte_selector

from .util import bfh, bh2u, to_string
from . import version
from .util import print_error, InvalidPassword, assert_bytes, to_bytes, inv_dict
from .util import unpack_uint16_from, unpack_uint32_from, unpack_uint64_from, unpack_int32_from, unpack_int64_from
from . import segwit_addr


def read_json_dict(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    try:
        r = json.loads(open(path, 'r').read())
    except:
        r = {}
    return r


BITCOIN_ADDRTYPE_P2PKH = 0
BITCOIN_ADDRTYPE_P2SH = 5

# RECRYPT network constants
TESTNET = False
ADDRTYPE_P2PKH = 0x3a
ADDRTYPE_P2SH = 0x32
WIF_PREFIX = 0x80
SEGWIT_HRP = "bc"
HEADERS_URL = ""
GENESIS = "000075aef83cf2853580f8ae8ce6f8c3096cfa21d98334d6e3f95e5582ed986c"
GENESIS_BITS = 0x1f00ffff
BASIC_HEADER_SIZE = 180  # not include sig
SERVERLIST = 'servers.json'
DEFAULT_SERVERS = read_json_dict(SERVERLIST)
DEFAULT_PORTS = {'t': '50001', 's': '50002'}
POW_BLOCK_COUNT = 5000
CHUNK_SIZE = 2016
POW_LIMIT = 0x0000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
POS_LIMIT = 0x00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff
POW_TARGET_TIMESPAN = 16 * 60  # bitcoin is 14 * 24 * 60 * 60
POW_TARGET_TIMESPACE = 2 * 64  # bitcoin is 10 * 60
RECOMMEND_CONFIRMATIONS = 10

# Version numbers for BIP32 extended keys
# standard: xprv, xpub
# segwit in p2sh: yprv, ypub
# native segwit: zprv, zpub
XPRV_HEADERS = {
    'standard': 0x0488ade4,
    'p2wpkh-p2sh': 0x049d7878,
    'p2wsh-p2sh': 0x295b005,
    'p2wpkh': 0x4b2430c,
    'p2wsh': 0x2aa7a99
}
XPUB_HEADERS = {
    'standard': 0x0488b21e,
    'p2wpkh-p2sh': 0x049d7cb2,
    'p2wsh-p2sh': 0x295b43f,
    'p2wpkh': 0x4b24746,
    'p2wsh': 0x2aa7ed3
}


def set_testnet():
    global ADDRTYPE_P2PKH, ADDRTYPE_P2SH, WIF_PREFIX
    global TESTNET, SERVERLIST, DEFAULT_PORTS, DEFAULT_SERVERS
    global GENESIS, GENESIS_BITS
    global SEGWIT_HRP
    global XPUB_HEADERS, XPRV_HEADERS
    TESTNET = True
    ADDRTYPE_P2PKH = 120
    ADDRTYPE_P2SH = 110
    SEGWIT_HRP = "tb"
    WIF_PREFIX = 0xef
    GENESIS = "0000e803ee215c0684ca0d2f9220594d3f828617972aad66feb2ba51f5e14222"
    GENESIS_BITS = 0x1f00ffff
    SERVERLIST = 'servers_testnet.json'
    DEFAULT_SERVERS = read_json_dict(SERVERLIST)
    DEFAULT_PORTS = {'t': '51001', 's': '51002'}
    XPRV_HEADERS = {
        'standard': 0x04358394,
        'p2wpkh-p2sh': 0x044a4e28,
        'p2wsh-p2sh': 0x024285b5,
        'p2wpkh': 0x045f18bc,
        'p2wsh': 0x02575048
    }
    XPUB_HEADERS = {
        'standard': 0x043587cf,
        'p2wpkh-p2sh': 0x044a5262,
        'p2wsh-p2sh': 0x024289ef,
        'p2wpkh': 0x045f1cf6,
        'p2wsh': 0x02575483
    }


mainnet_block_explorers = {
    'recrypt.info': ('https://recrypt.info',
                  {'tx': 'tx', 'addr': 'address', 'contract': 'contract'}),
    'explorer.recrypt.org': ('https://explorer.recrypt.org',
                          {'tx': 'tx', 'addr': 'address', 'contract': 'contract'}),
    'recryptexplorer.io': ('https://recryptexplorer.io/',
                        {'tx': 'tx', 'addr': 'address', 'contract': 'contract'}),
}

testnet_block_explorers = {
    'recrypt.info': ('https://testnet.recrypt.info',
                  {'tx': 'tx', 'addr': 'address', 'contract': 'contract'}),
    'explorer.recrypt.org': ('https://testnet.recrypt.org/',
                          {'tx': 'tx', 'addr': 'address', 'contract': 'contract'}),
}


################################## transactions

MAX_FEE_RATE = 1250000
# min fee rate is set to 0.4*MAX_FEE_RATE

FEE_TARGETS = [25, 10, 5, 2]

COINBASE_MATURITY = 500
COIN = 100000000

# supported types of transction outputs
TYPE_ADDRESS = 0
TYPE_PUBKEY  = 1
TYPE_SCRIPT  = 2

# AES encryption

try:
    from Cryptodome.Cipher import AES
except:
    AES = None


class InvalidPadding(Exception):
    pass


def append_PKCS7_padding(data):
    assert_bytes(data)
    padlen = 16 - (len(data) % 16)
    return data + bytes([padlen]) * padlen


def strip_PKCS7_padding(data):
    assert_bytes(data)
    if len(data) % 16 != 0 or len(data) == 0:
        raise InvalidPadding("invalid length")
    padlen = data[-1]
    if padlen > 16:
        raise InvalidPadding("invalid padding byte (large)")
    for i in data[-padlen:]:
        if i != padlen:
            raise InvalidPadding("invalid padding byte (inconsistent)")
    return data[0:-padlen]


def aes_encrypt_with_iv(key, iv, data):
    assert_bytes(key, iv, data)
    data = append_PKCS7_padding(data)
    if AES:
        e = AES.new(key, AES.MODE_CBC, iv).encrypt(data)
    else:
        aes_cbc = pyaes.AESModeOfOperationCBC(key, iv=iv)
        aes = pyaes.Encrypter(aes_cbc, padding=pyaes.PADDING_NONE)
        e = aes.feed(data) + aes.feed()  # empty aes.feed() flushes buffer
    return e


def aes_decrypt_with_iv(key, iv, data):
    assert_bytes(key, iv, data)
    if AES:
        cipher = AES.new(key, AES.MODE_CBC, iv)
        data = cipher.decrypt(data)
    else:
        aes_cbc = pyaes.AESModeOfOperationCBC(key, iv=iv)
        aes = pyaes.Decrypter(aes_cbc, padding=pyaes.PADDING_NONE)
        data = aes.feed(data) + aes.feed()  # empty aes.feed() flushes buffer
    try:
        return strip_PKCS7_padding(data)
    except InvalidPadding:
        raise InvalidPassword()


def EncodeAES(secret, s):
    assert_bytes(s)
    iv = bytes(os.urandom(16))
    # aes_cbc = pyaes.AESModeOfOperationCBC(secret, iv=iv)
    # aes = pyaes.Encrypter(aes_cbc)
    # e = iv + aes.feed(s) + aes.feed()
    ct = aes_encrypt_with_iv(secret, iv, s)
    e = iv + ct
    return base64.b64encode(e)


def DecodeAES(secret, e):
    e = bytes(base64.b64decode(e))
    iv, e = e[:16], e[16:]
    # aes_cbc = pyaes.AESModeOfOperationCBC(secret, iv=iv)
    # aes = pyaes.Decrypter(aes_cbc)
    # s = aes.feed(e) + aes.feed()
    s = aes_decrypt_with_iv(secret, iv, e)
    return s


def pw_encode(s, password):
    if password:
        secret = Hash(password)
        return EncodeAES(secret, to_bytes(s, "utf8")).decode('utf8')
    else:
        return s


def pw_decode(s, password):
    if password is not None:
        secret = Hash(password)
        try:
            d = to_string(DecodeAES(secret, s), "utf8")
        except Exception:
            raise InvalidPassword()
        return d
    else:
        return s


def rev_hex(s):
    return bh2u(bfh(s)[::-1])


def int_to_hex(i, length=1):
    assert isinstance(i, int)
    if i < 0:
        i = pow(256, length) + i
    s = hex(i)[2:].rstrip('L')
    s = "0"*(2*length - len(s)) + s
    return rev_hex(s)


def script_num_to_hex(i: int) -> str:
    """See CScriptNum in Bitcoin Core.
    Encodes an integer as hex, to be used in script.

    ported from https://github.com/bitcoin/bitcoin/blob/8cbc5c4be4be22aca228074f087a374a7ec38be8/src/script/script.h#L326
    """
    if i == 0:
        return ''

    result = bytearray()
    neg = i < 0
    absvalue = abs(i)
    while absvalue > 0:
        result.append(absvalue & 0xff)
        absvalue >>= 8

    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80

    return bh2u(result)


def var_int(i: int) -> str:
    # https://en.bitcoin.it/wiki/Protocol_specification#Variable_length_integer
    if i<0xfd:
        return int_to_hex(i)
    elif i<=0xffff:
        return "fd"+int_to_hex(i,2)
    elif i<=0xffffffff:
        return "fe"+int_to_hex(i,4)
    else:
        return "ff"+int_to_hex(i,8)


def witness_push(item: str) -> str:
    """Returns data in the form it should be present in the witness.
    hex -> hex
    """
    return var_int(len(item) // 2) + item


def op_push(i: int) -> str:
    if i < 0x4c:  # OP_PUSHDATA1
        return int_to_hex(i)
    elif i <= 0xff:
        return '4c' + int_to_hex(i)
    elif i <= 0xffff:
        return '4d' + int_to_hex(i,2)
    else:
        return '4e' + int_to_hex(i,4)


def push_script(data: str) -> str:
    """Returns pushed data to the script, automatically
    choosing canonical opcodes depending on the length of the data.
    hex -> hex

    ported from https://github.com/btcsuite/btcd/blob/fdc2bc867bda6b351191b5872d2da8270df00d13/txscript/scriptbuilder.go#L128
    """
    data = bfh(data)
    from .transaction import opcodes

    data_len = len(data)

    # "small integer" opcodes
    if data_len == 0 or data_len == 1 and data[0] == 0:
        return bh2u(bytes([opcodes.OP_0]))
    elif data_len == 1 and data[0] <= 16:
        return bh2u(bytes([opcodes.OP_1 - 1 + data[0]]))
    elif data_len == 1 and data[0] == 0x81:
        return bh2u(bytes([opcodes.OP_1NEGATE]))

    return op_push(data_len) + bh2u(data)

def add_number_to_script(i: int) -> bytes:
    return bfh(push_script(script_num_to_hex(i)))

def sha256(x):
    x = to_bytes(x, 'utf8')
    return bytes(hashlib.sha256(x).digest())


def Hash(x):
    x = to_bytes(x, 'utf8')
    out = bytes(sha256(sha256(x)))
    return out


hash_encode = lambda x: bh2u(x[::-1])
hash_decode = lambda x: bfh(x)[::-1]
hmac_sha_512 = lambda x, y: hmac.new(x, y, hashlib.sha512).digest()


def is_new_seed(x, prefix=version.SEED_PREFIX):
    from . import mnemonic
    x = mnemonic.normalize_text(x)
    s = bh2u(hmac_sha_512(b"Seed version", x.encode('utf8')))
    return s.startswith(prefix)


def is_old_seed(seed):
    from . import old_mnemonic
    words = seed.strip().split()
    try:
        old_mnemonic.mn_decode(words)
        uses_electrum_words = True
    except Exception:
        uses_electrum_words = False
    try:
        seed = bfh(seed)
        is_hex = (len(seed) == 16 or len(seed) == 32)
    except Exception:
        is_hex = False
    return is_hex or (uses_electrum_words and (len(words) == 12 or len(words) == 24))


def seed_type(x):
    # if is_old_seed(x):
    #     return 'old'
    if is_new_seed(x):
        return 'standard'
    elif is_new_seed(x, version.SEED_PREFIX_SW):
        return 'segwit'
    # elif is_new_seed(x, version.SEED_PREFIX_2FA):
    #     # disable 2fa for now
    #     return '2fa'
    return ''

is_seed = lambda x: bool(seed_type(x))

# pywallet openssl private key implementation


def i2o_ECPublicKey(pubkey, compressed=False):
    # public keys are 65 bytes long (520 bits)
    # 0x04 + 32-byte X-coordinate + 32-byte Y-coordinate
    # 0x00 = point at infinity, 0x02 and 0x03 = compressed, 0x04 = uncompressed
    # compressed keys: <sign> <x> where <sign> is 0x02 if y is even and 0x03 if y is odd
    if compressed:
        if pubkey.point.y() & 1:
            key = '03' + '%064x' % pubkey.point.x()
        else:
            key = '02' + '%064x' % pubkey.point.x()
    else:
        key = '04' + \
              '%064x' % pubkey.point.x() + \
              '%064x' % pubkey.point.y()

    return bfh(key)
# end pywallet openssl private key implementation


############ functions from pywallet #####################
def hash_160(public_key):
    try:
        md = hashlib.new('ripemd160')
        md.update(sha256(public_key))
        return md.digest()
    except BaseException:
        from . import ripemd
        md = ripemd.new(sha256(public_key))
        return md.digest()


def hash160_to_b58_address(h160, addrtype, witness_program_version=1):
    s = bytes([addrtype])
    s += h160
    return base_encode(s+Hash(s)[0:4], base=58)


def b58_address_to_hash160(addr):
    addr = to_bytes(addr, 'ascii')
    _bytes = base_decode(addr, 25, base=58)
    return _bytes[0], _bytes[1:21]


def hash160_to_p2pkh(h160):
    return hash160_to_b58_address(h160, ADDRTYPE_P2PKH)


def hash160_to_p2sh(h160):
    return hash160_to_b58_address(h160, ADDRTYPE_P2SH)


def public_key_to_p2pkh(public_key):
    return hash160_to_p2pkh(hash_160(public_key))


def hash160_to_segwit_addr(h160):
    return segwit_addr.encode(SEGWIT_HRP, 0, h160)


def hash_to_segwit_addr(h, witver):
    return segwit_addr.encode(SEGWIT_HRP, witver, h)


def public_key_to_p2wpkh(public_key):
    return hash_to_segwit_addr(hash_160(public_key), witver=0)


def script_to_p2wsh(script):
    return hash_to_segwit_addr(sha256(bfh(script)), witver=0)


def p2wpkh_nested_script(pubkey):
    pkh = bh2u(hash_160(bfh(pubkey)))
    return '00' + push_script(pkh)


def p2wsh_nested_script(witness_script):
    wsh = bh2u(sha256(bfh(witness_script)))
    return '00' + push_script(wsh)


def pubkey_to_address(txin_type, pubkey):
    if txin_type == 'p2pkh':
        return public_key_to_p2pkh(bfh(pubkey))
    elif txin_type == 'p2wpkh':
        return public_key_to_p2wpkh(bfh(pubkey))
    elif txin_type == 'p2wpkh-p2sh':
        scriptSig = p2wpkh_nested_script(pubkey)
        return hash160_to_p2sh(hash_160(bfh(scriptSig)))
    else:
        raise NotImplementedError(txin_type)


def redeem_script_to_address(txin_type, redeem_script):
    if txin_type == 'p2sh':
        return hash160_to_p2sh(hash_160(bfh(redeem_script)))
    elif txin_type == 'p2wsh':
        return script_to_p2wsh(redeem_script)
    elif txin_type == 'p2wsh-p2sh':
        scriptSig = p2wsh_nested_script(redeem_script)
        return hash160_to_p2sh(hash_160(bfh(scriptSig)))
    else:
        raise NotImplementedError(txin_type)


def address_to_script(addr):
    witver, witprog = segwit_addr.decode(SEGWIT_HRP, addr)
    if witprog is not None:
        assert (0 <= witver <= 16)
        OP_n = witver + 0x50 if witver > 0 else 0
        script = bh2u(bytes([OP_n]))
        script += push_script(bh2u(bytes(witprog)))
        return script
    addrtype, hash_160 = b58_address_to_hash160(addr)
    if addrtype == ADDRTYPE_P2PKH:
        script = '76a9'                                      # op_dup, op_hash_160
        script += push_script(bh2u(hash_160))
        script += '88ac'                                     # op_equalverify, op_checksig
    elif addrtype == ADDRTYPE_P2SH:
        script = 'a9'                                        # op_hash_160
        script += push_script(bh2u(hash_160))
        script += '87'                                       # op_equal
    else:
        raise Exception('unknown address type')
    return script

def address_to_scripthash(addr):
    script = address_to_script(addr)
    return script_to_scripthash(script)


def script_to_scripthash(script):
    h = sha256(bytes.fromhex(script))[0:32]
    return bh2u(bytes(reversed(h)))

def public_key_to_p2pk_script(pubkey):
    script = push_script(pubkey)
    script += 'ac'
    return script


__b58chars = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
assert len(__b58chars) == 58

__b43chars = b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$*+-./:'
assert len(__b43chars) == 43


def base_encode(v, base):
    """ encode v, which is a string of bytes, to base58."""
    assert_bytes(v)
    assert base in (58, 43)
    chars = __b58chars
    if base == 43:
        chars = __b43chars
    long_value = 0
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * c
    result = bytearray()
    while long_value >= base:
        div, mod = divmod(long_value, base)
        result.append(chars[mod])
        long_value = div
    result.append(chars[long_value])
    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == 0x00:
            nPad += 1
        else:
            break
    result.extend([chars[0]] * nPad)
    result.reverse()
    return result.decode('ascii')


def base_decode(v, length, base):
    """ decode v into a string of len bytes."""
    # assert_bytes(v)
    v = to_bytes(v, 'ascii')
    assert base in (58, 43)
    chars = __b58chars
    if base == 43:
        chars = __b43chars
    long_value = 0
    for (i, c) in enumerate(v[::-1]):
        digit = chars.find(bytes([c]))
        if digit == -1:
            raise ValueError('Forbidden character {} for base {}'.format(c, base))
        long_value += digit * (base ** i)
    result = bytearray()
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result.append(mod)
        long_value = div
    result.append(long_value)
    nPad = 0
    for c in v:
        if c == chars[0]:
            nPad += 1
        else:
            break
    result.extend(b'\x00' * nPad)
    if length is not None and len(result) != length:
        return None
    result.reverse()
    return bytes(result)


class InvalidChecksum(Exception):
    pass

def EncodeBase58Check(vchIn):
    hash = Hash(vchIn)
    return base_encode(vchIn + hash[0:4], base=58)


def DecodeBase58Check(psz):
    vchRet = base_decode(psz, None, base=58)
    key = vchRet[0:-4]
    csum = vchRet[-4:]
    hash = Hash(key)
    cs32 = hash[0:4]
    if cs32 != csum:
        raise InvalidChecksum('expected {}, actual {}'.format(bh2u(cs32), bh2u(csum)))
    else:
        return key


# extended key export format for segwit

SCRIPT_TYPES = {
    'p2pkh': 0,
    'p2wpkh': 1,
    'p2wpkh-p2sh': 2,
    'p2sh': 5,
    'p2wsh': 6,
    'p2wsh-p2sh': 7
}


def serialize_privkey(secret, compressed, txin_type, internal_use=False):
    if internal_use:
        prefix = bytes([(SCRIPT_TYPES[txin_type] + WIF_PREFIX) & 255])
    else:
        prefix = bytes([WIF_PREFIX])
    suffix = b'\01' if compressed else b''
    vchIn = prefix + secret + suffix
    base58_wif = EncodeBase58Check(vchIn)
    if internal_use:
        return base58_wif
    return '{}:{}'.format(txin_type, base58_wif)


def deserialize_privkey(key):
    if is_minikey(key):
        return 'p2pkh', minikey_to_private_key(key), True

    txin_type = None
    if ':' in key:
        txin_type, key = key.split(sep=':', maxsplit=1)
        assert txin_type in SCRIPT_TYPES
    try:
        vch = DecodeBase58Check(key)
    except BaseException:
        neutered_privkey = str(key)[:3] + '..' + str(key)[-2:]
        raise Exception("cannot deserialize", neutered_privkey)

    if txin_type is None:
        # keys exported in version 3.0.x encoded script type in first byte
        txin_type = inv_dict(SCRIPT_TYPES)[vch[0] - WIF_PREFIX]
    else:
        assert vch[0] == WIF_PREFIX

    assert len(vch) in [33, 34]
    compressed = len(vch) == 34
    return txin_type, vch[1:33], compressed


def regenerate_key(pk):
    assert len(pk) == 32
    return EC_KEY(pk)


def GetPubKey(pubkey, compressed=False):
    return i2o_ECPublicKey(pubkey, compressed)


def GetSecret(pkey):
    return bfh('%064x' % pkey.secret)


def is_compressed(sec):
    return deserialize_privkey(sec)[2]


def public_key_from_private_key(pk, compressed):
    pkey = regenerate_key(pk)
    public_key = GetPubKey(pkey.pubkey, compressed)
    return bh2u(public_key)


def address_from_private_key(sec):
    txin_type, privkey, compressed = deserialize_privkey(sec)
    public_key = public_key_from_private_key(privkey, compressed)
    address = pubkey_to_address(txin_type, public_key)
    return address


def is_segwit_address(addr):
    try:
        witver, witprog = segwit_addr.decode(SEGWIT_HRP, addr)
        return witprog is not None
    except (BaseException,) as e:
        return False


def is_b58_address(addr):
    try:
        addrtype, h = b58_address_to_hash160(addr)
    except Exception as e:
        return False
    if addrtype not in [ADDRTYPE_P2PKH, ADDRTYPE_P2SH]:
        return False
    return addr == hash160_to_b58_address(h, addrtype)


def is_address(addr):
    return is_segwit_address(addr) or is_b58_address(addr)


def is_p2pkh(addr):
    if is_address(addr):
        addrtype, h = b58_address_to_hash160(addr)
        return addrtype == ADDRTYPE_P2PKH


def is_p2sh(addr):
    if is_address(addr):
        addrtype, h = b58_address_to_hash160(addr)
        return addrtype == ADDRTYPE_P2SH


def is_private_key(key):
    try:
        k = deserialize_privkey(key)
        return k is not False
    except:
        return False


def is_hash160(addr):
    if not addr:
        return False
    if not isinstance(addr, str):
        return False
    if not len(addr) == 40:
        return False
    for char in addr:
        if (char < '0' or char > '9') and (char < 'A' or char > 'F') and (char < 'a' or char > 'f'):
            return False
    return True



########### end pywallet functions #######################

def is_minikey(text):
    # Minikeys are typically 22 or 30 characters, but this routine
    # permits any length of 20 or more provided the minikey is valid.
    # A valid minikey must begin with an 'S', be in base58, and when
    # suffixed with '?' have its SHA256 hash begin with a zero byte.
    # They are widely used in Casascius physical bitoins.
    return (len(text) >= 20 and text[0] == 'S'
            and all(ord(c) in __b58chars for c in text)
            and sha256(text + '?')[0] == 0x00)


def minikey_to_private_key(text):
    return sha256(text)

from ecdsa.ecdsa import curve_secp256k1, generator_secp256k1
from ecdsa.curves import SECP256k1
from ecdsa.ellipticcurve import Point
from ecdsa.util import string_to_number, number_to_string


def msg_magic(message):
    length = bfh(var_int(len(message)))
    return b"\x15Recrypt Signed Message:\n" + length + message


def verify_message(address, sig, message):
    assert_bytes(sig, message)
    try:
        h = Hash(msg_magic(message))
        public_key, compressed = pubkey_from_signature(sig, h)
        # check public key using the address
        pubkey = point_to_ser(public_key.pubkey.point, compressed)
        for txin_type in ['p2pkh', 'p2wpkh', 'p2wpkh-p2sh']:
            addr = pubkey_to_address(txin_type, bh2u(pubkey))
            if address == addr:
                break
        else:
            raise Exception("Bad signature")
        # check message
        public_key.verify_digest(sig[1:], h, sigdecode = ecdsa.util.sigdecode_string)
        return True
    except Exception as e:
        print_error("Verification error: {0}".format(e))
        return False


def encrypt_message(message, pubkey, magic=b'BIE1'):
    return EC_KEY.encrypt_message(message, bfh(pubkey), magic)


def chunks(l, n):
    return [l[i:i+n] for i in range(0, len(l), n)]


def ECC_YfromX(x,curved=curve_secp256k1, odd=True):
    _p = curved.p()
    _a = curved.a()
    _b = curved.b()
    for offset in range(128):
        Mx = x + offset
        My2 = pow(Mx, 3, _p) + _a * pow(Mx, 2, _p) + _b % _p
        My = pow(My2, (_p+1)//4, _p )

        if curved.contains_point(Mx,My):
            if odd == bool(My&1):
                return [My,offset]
            return [_p-My,offset]
    raise Exception('ECC_YfromX: No Y found')


def negative_point(P):
    return Point( P.curve(), P.x(), -P.y(), P.order() )


def point_to_ser(P, comp=True ):
    if comp:
        return bfh( ('%02x'%(2+(P.y()&1)))+('%064x'%P.x()) )
    return bfh( '04'+('%064x'%P.x())+('%064x'%P.y()) )


def ser_to_point(Aser):
    curve = curve_secp256k1
    generator = generator_secp256k1
    _r  = generator.order()
    assert Aser[0] in [0x02, 0x03, 0x04]
    if Aser[0] == 0x04:
        return Point( curve, string_to_number(Aser[1:33]), string_to_number(Aser[33:]), _r )
    Mx = string_to_number(Aser[1:])
    return Point( curve, Mx, ECC_YfromX(Mx, curve, Aser[0] == 0x03)[0], _r )


class MyVerifyingKey(ecdsa.VerifyingKey):
    @classmethod
    def from_signature(klass, sig, recid, h, curve):
        """ See http://www.secg.org/download/aid-780/sec1-v2.pdf, chapter 4.1.6 """
        from ecdsa import util, numbertheory
        from . import msqr
        curveFp = curve.curve
        G = curve.generator
        order = G.order()
        # extract r,s from signature
        r, s = util.sigdecode_string(sig, order)
        # 1.1
        x = r + (recid//2) * order
        # 1.3
        alpha = ( x * x * x  + curveFp.a() * x + curveFp.b() ) % curveFp.p()
        beta = msqr.modular_sqrt(alpha, curveFp.p())
        y = beta if (beta - recid) % 2 == 0 else curveFp.p() - beta
        # 1.4 the constructor checks that nR is at infinity
        R = Point(curveFp, x, y, order)
        # 1.5 compute e from message:
        e = string_to_number(h)
        minus_e = -e % order
        # 1.6 compute Q = r^-1 (sR - eG)
        inv_r = numbertheory.inverse_mod(r,order)
        Q = inv_r * ( s * R + minus_e * G )
        return klass.from_public_point( Q, curve )


def pubkey_from_signature(sig, h):
    if len(sig) != 65:
        raise Exception("Wrong encoding")
    nV = sig[0]
    if nV < 27 or nV >= 35:
        raise Exception("Bad encoding")
    if nV >= 31:
        compressed = True
        nV -= 4
    else:
        compressed = False
    recid = nV - 27
    return MyVerifyingKey.from_signature(sig[1:], recid, h, curve = SECP256k1), compressed


class MySigningKey(ecdsa.SigningKey):
    """Enforce low S values in signatures"""

    def sign_number(self, number, entropy=None, k=None):
        curve = SECP256k1
        G = curve.generator
        order = G.order()
        r, s = ecdsa.SigningKey.sign_number(self, number, entropy, k)
        if s > order//2:
            s = order - s
        return r, s


class EC_KEY(object):

    def __init__( self, k ):
        secret = string_to_number(k)
        self.pubkey = ecdsa.ecdsa.Public_key( generator_secp256k1, generator_secp256k1 * secret )
        self.privkey = ecdsa.ecdsa.Private_key( self.pubkey, secret )
        self.secret = secret

    def get_public_key(self, compressed=True):
        return bh2u(point_to_ser(self.pubkey.point, compressed))

    def sign(self, msg_hash):
        private_key = MySigningKey.from_secret_exponent(self.secret, curve = SECP256k1)
        public_key = private_key.get_verifying_key()
        signature = private_key.sign_digest_deterministic(msg_hash, hashfunc=hashlib.sha256, sigencode = ecdsa.util.sigencode_string)
        assert public_key.verify_digest(signature, msg_hash, sigdecode = ecdsa.util.sigdecode_string)
        return signature

    def sign_message(self, message, is_compressed):
        message = to_bytes(message, 'utf8')
        signature = self.sign(Hash(msg_magic(message)))
        for i in range(4):
            sig = bytes([27 + i + (4 if is_compressed else 0)]) + signature
            try:
                self.verify_message(sig, message)
                return sig
            except Exception as e:
                continue
        else:
            raise Exception("error: cannot sign message")

    def verify_message(self, sig, message):
        assert_bytes(message)
        h = Hash(msg_magic(message))
        public_key, compressed = pubkey_from_signature(sig, h)
        # check public key
        if point_to_ser(public_key.pubkey.point, compressed) != point_to_ser(self.pubkey.point, compressed):
            raise Exception("Bad signature")
        # check message
        public_key.verify_digest(sig[1:], h, sigdecode = ecdsa.util.sigdecode_string)


    # ECIES encryption/decryption methods; AES-128-CBC with PKCS7 is used as the cipher; hmac-sha256 is used as the mac

    @classmethod
    def encrypt_message(self, message, pubkey, magic=b'BIE1'):
        assert_bytes(message)

        pk = ser_to_point(pubkey)
        if not ecdsa.ecdsa.point_is_valid(generator_secp256k1, pk.x(), pk.y()):
            raise Exception('invalid pubkey')

        ephemeral_exponent = number_to_string(ecdsa.util.randrange(pow(2,256)), generator_secp256k1.order())
        ephemeral = EC_KEY(ephemeral_exponent)
        ecdh_key = point_to_ser(pk * ephemeral.privkey.secret_multiplier)
        key = hashlib.sha512(ecdh_key).digest()
        iv, key_e, key_m = key[0:16], key[16:32], key[32:]
        ciphertext = aes_encrypt_with_iv(key_e, iv, message)
        ephemeral_pubkey = bfh(ephemeral.get_public_key(compressed=True))
        encrypted = magic + ephemeral_pubkey + ciphertext
        mac = hmac.new(key_m, encrypted, hashlib.sha256).digest()

        return base64.b64encode(encrypted + mac)

    def decrypt_message(self, encrypted, magic=b'BIE1'):
        encrypted = base64.b64decode(encrypted)
        if len(encrypted) < 85:
            raise Exception('invalid ciphertext: length')
        magic_found = encrypted[:4]
        ephemeral_pubkey = encrypted[4:37]
        ciphertext = encrypted[37:-32]
        mac = encrypted[-32:]
        if magic_found != magic:
            raise Exception('invalid ciphertext: invalid magic bytes')
        try:
            ephemeral_pubkey = ser_to_point(ephemeral_pubkey)
        except AssertionError as e:
            raise Exception('invalid ciphertext: invalid ephemeral pubkey')
        if not ecdsa.ecdsa.point_is_valid(generator_secp256k1, ephemeral_pubkey.x(), ephemeral_pubkey.y()):
            raise Exception('invalid ciphertext: invalid ephemeral pubkey')
        ecdh_key = point_to_ser(ephemeral_pubkey * self.privkey.secret_multiplier)
        key = hashlib.sha512(ecdh_key).digest()
        iv, key_e, key_m = key[0:16], key[16:32], key[32:]
        if mac != hmac.new(key_m, encrypted[:-32], hashlib.sha256).digest():
            raise InvalidPassword()
        return aes_decrypt_with_iv(key_e, iv, ciphertext)


###################################### BIP32 ##############################

random_seed = lambda n: "%032x"%ecdsa.util.randrange( pow(2,n) )
BIP32_PRIME = 0x80000000


def get_pubkeys_from_secret(secret):
    # public key
    private_key = ecdsa.SigningKey.from_string( secret, curve = SECP256k1 )
    public_key = private_key.get_verifying_key()
    K = public_key.to_string()
    K_compressed = GetPubKey(public_key.pubkey,True)
    return K, K_compressed


# Child private key derivation function (from master private key)
# k = master private key (32 bytes)
# c = master chain code (extra entropy for key derivation) (32 bytes)
# n = the index of the key we want to derive. (only 32 bits will be used)
# If n is negative (i.e. the 32nd bit is set), the resulting private key's
#  corresponding public key can NOT be determined without the master private key.
# However, if n is positive, the resulting private key's corresponding
#  public key can be determined without the master private key.
def CKD_priv(k, c, n):
    is_prime = n & BIP32_PRIME
    return _CKD_priv(k, c, bfh(rev_hex(int_to_hex(n,4))), is_prime)


def _CKD_priv(k, c, s, is_prime):
    order = generator_secp256k1.order()
    keypair = EC_KEY(k)
    cK = GetPubKey(keypair.pubkey,True)
    data = bytes([0]) + k + s if is_prime else cK + s
    I = hmac.new(c, data, hashlib.sha512).digest()
    k_n = number_to_string( (string_to_number(I[0:32]) + string_to_number(k)) % order , order )
    c_n = I[32:]
    return k_n, c_n

# Child public key derivation function (from public key only)
# K = master public key
# c = master chain code
# n = index of key we want to derive
# This function allows us to find the nth public key, as long as n is
#  non-negative. If n is negative, we need the master private key to find it.
def CKD_pub(cK, c, n):
    if n & BIP32_PRIME:
        raise Exception('CKD_pub error')
    return _CKD_pub(cK, c, bfh(rev_hex(int_to_hex(n,4))))

# helper function, callable with arbitrary string
def _CKD_pub(cK, c, s):
    order = generator_secp256k1.order()
    I = hmac.new(c, cK + s, hashlib.sha512).digest()
    curve = SECP256k1
    pubkey_point = string_to_number(I[0:32])*curve.generator + ser_to_point(cK)
    public_key = ecdsa.VerifyingKey.from_public_point( pubkey_point, curve = SECP256k1 )
    c_n = I[32:]
    cK_n = GetPubKey(public_key.pubkey,True)
    return cK_n, c_n


def xprv_header(xtype):
    return bfh("%08x" % (XPRV_HEADERS[xtype]))


def xpub_header(xtype):
    return bfh("%08x" % (XPUB_HEADERS[xtype]))


def serialize_xprv(xtype, c, k, depth=0, fingerprint=b'\x00'*4, child_number=b'\x00'*4):
    xprv = xprv_header(xtype) + bytes([depth]) + fingerprint + child_number + c + bytes([0]) + k
    return EncodeBase58Check(xprv)


def serialize_xpub(xtype, c, cK, depth=0, fingerprint=b'\x00'*4, child_number=b'\x00'*4):
    xpub = xpub_header(xtype) + bytes([depth]) + fingerprint + child_number + c + cK
    return EncodeBase58Check(xpub)


def deserialize_xkey(xkey, prv):
    xkey = DecodeBase58Check(xkey)
    if not xkey or len(xkey) != 78:
        raise Exception('Invalid xkey', xkey)
    depth = xkey[4]
    fingerprint = xkey[5:9]
    child_number = xkey[9:13]
    c = xkey[13:13+32]
    header = int('0x' + bh2u(xkey[0:4]), 16)
    headers = XPRV_HEADERS if prv else XPUB_HEADERS
    if header not in headers.values():
        raise Exception('Invalid xpub format', hex(header))
    xtype = list(headers.keys())[list(headers.values()).index(header)]
    n = 33 if prv else 32
    K_or_k = xkey[13+n:]
    return xtype, depth, fingerprint, child_number, c, K_or_k


def deserialize_xpub(xkey):
    return deserialize_xkey(xkey, False)

def deserialize_xprv(xkey):
    return deserialize_xkey(xkey, True)


def xpub_type(x):
    return deserialize_xpub(x)[0]

def is_xpub(text):
    try:
        deserialize_xpub(text)
        return True
    except:
        return False


def is_xprv(text):
    try:
        deserialize_xprv(text)
        return True
    except:
        return False


def xpub_from_xprv(xprv):
    xtype, depth, fingerprint, child_number, c, k = deserialize_xprv(xprv)
    K, cK = get_pubkeys_from_secret(k)
    return serialize_xpub(xtype, c, cK, depth, fingerprint, child_number)


def bip32_root(seed, xtype):
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    master_k = I[0:32]
    master_c = I[32:]
    K, cK = get_pubkeys_from_secret(master_k)
    xprv = serialize_xprv(xtype, master_c, master_k)
    xpub = serialize_xpub(xtype, master_c, cK)
    return xprv, xpub


def xpub_from_pubkey(xtype, cK):
    assert cK[0] in [0x02, 0x03]
    return serialize_xpub(xtype, b'\x00'*32, cK)


def bip32_derivation(s):
    assert s.startswith('m/')
    s = s[2:]
    for n in s.split('/'):
        if n == '': continue
        i = int(n[:-1]) + BIP32_PRIME if n[-1] == "'" else int(n)
        yield i


def is_bip32_derivation(x):
    try:
        [ i for i in bip32_derivation(x)]
        return True
    except :
        return False

def bip32_private_derivation(xprv, branch, sequence):
    assert sequence.startswith(branch)
    if branch == sequence:
        return xprv, xpub_from_xprv(xprv)
    xtype, depth, fingerprint, child_number, c, k = deserialize_xprv(xprv)
    sequence = sequence[len(branch):]
    for n in sequence.split('/'):
        if n == '': continue
        i = int(n[:-1]) + BIP32_PRIME if n[-1] == "'" else int(n)
        parent_k = k
        k, c = CKD_priv(k, c, i)
        depth += 1
    _, parent_cK = get_pubkeys_from_secret(parent_k)
    fingerprint = hash_160(parent_cK)[0:4]
    child_number = bfh("%08X"%i)
    K, cK = get_pubkeys_from_secret(k)
    xpub = serialize_xpub(xtype, c, cK, depth, fingerprint, child_number)
    xprv = serialize_xprv(xtype, c, k, depth, fingerprint, child_number)
    return xprv, xpub


def bip32_public_derivation(xpub, branch, sequence):
    xtype, depth, fingerprint, child_number, c, cK = deserialize_xpub(xpub)
    assert sequence.startswith(branch)
    sequence = sequence[len(branch):]
    for n in sequence.split('/'):
        if n == '': continue
        i = int(n)
        parent_cK = cK
        cK, c = CKD_pub(cK, c, i)
        depth += 1
    fingerprint = hash_160(parent_cK)[0:4]
    child_number = bfh("%08X"%i)
    return serialize_xpub(xtype, c, cK, depth, fingerprint, child_number)


def bip32_private_key(sequence, k, chain):
    for i in sequence:
        k, chain = CKD_priv(k, chain, i)
    return k


class Deserializer(object):
    '''Deserializes blocks into transactions.

    External entry points are read_tx() and read_block().

    This code is performance sensitive as it is executed 100s of
    millions of times during sync.
    '''

    def __init__(self, binary, start=0):
        assert isinstance(binary, bytes)
        self.binary = binary
        self.binary_length = len(binary)
        self.cursor = start

    def read_byte(self):
        cursor = self.cursor
        self.cursor += 1
        return self.binary[cursor]

    def read_varbytes(self):
        return self._read_nbytes(self._read_varint())

    def read_varint(self):
        n = self.binary[self.cursor]
        self.cursor += 1
        if n < 253:
            return n
        if n == 253:
            return self._read_le_uint16()
        if n == 254:
            return self._read_le_uint32()
        return self._read_le_uint64()

    def _read_nbytes(self, n):
        cursor = self.cursor
        self.cursor = end = cursor + n
        assert self.binary_length >= end
        return self.binary[cursor:end]

    def _read_le_int32(self):
        result, = unpack_int32_from(self.binary, self.cursor)
        self.cursor += 4
        return result

    def _read_le_int64(self):
        result, = unpack_int64_from(self.binary, self.cursor)
        self.cursor += 8
        return result

    def _read_le_uint16(self):
        result, = unpack_uint16_from(self.binary, self.cursor)
        self.cursor += 2
        return result

    def _read_le_uint32(self):
        result, = unpack_uint32_from(self.binary, self.cursor)
        self.cursor += 4
        return result

    def _read_le_uint64(self):
        result, = unpack_uint64_from(self.binary, self.cursor)
        self.cursor += 8
        return result


def hash_header(header):
    if header is None:
        return '0' * 64
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00' * 32
    return hash_encode(Hash(bfh(serialize_header(header))))


def serialize_header(res):
    sig_length = len(res.get('sig'))//2
    s = int_to_hex(res.get('version'), 4) \
        + rev_hex(res.get('prev_block_hash')) \
        + rev_hex(res.get('merkle_root')) \
        + int_to_hex(int(res.get('timestamp')), 4) \
        + int_to_hex(int(res.get('bits')), 4) \
        + int_to_hex(int(res.get('nonce')), 4) \
        + rev_hex(res.get('hash_state_root')) \
        + rev_hex(res.get('hash_utxo_root')) \
        + rev_hex(res.get('hash_prevout_stake')) \
        + int_to_hex(int(res.get('hash_prevout_n')), 4) \
        + var_int(sig_length) \
        + (res.get('sig'))
    # print('serialize_header', res, '\n', s)
    return s


def deserialize_header(s, height):
    hex_to_int = lambda s: int('0x' + bh2u(s[::-1]), 16)
    deserializer = Deserializer(s, start=BASIC_HEADER_SIZE)
    sig_length = deserializer.read_varint()
    h = {
        'block_height': height,
        'version': hex_to_int(s[0:4]),
        'prev_block_hash': hash_encode(s[4:36]),
        'merkle_root': hash_encode(s[36:68]),
        'timestamp': hex_to_int(s[68:72]),
        'bits': hex_to_int(s[72:76]),
        'nonce': hex_to_int(s[76:80]),
        'hash_state_root': hash_encode(s[80:112]),
        'hash_utxo_root': hash_encode(s[112:144]),
        'hash_prevout_stake': hash_encode(s[144:176]),
        'hash_prevout_n': hex_to_int(s[176:180]),
        'sig': hash_encode(s[:-sig_length - 1:-1]),
    }
    return h


def read_a_raw_header_from_chunk(data, start):
    deserializer = Deserializer(data, start=start+BASIC_HEADER_SIZE)
    sig_length = deserializer.read_varint()
    cursor = deserializer.cursor + sig_length
    return data[start: cursor], cursor


def is_pos(header):
    hash_prevout_stake = header.get('hash_prevout_stake', None)
    hash_prevout_n = header.get('hash_prevout_n', 0)
    return hash_prevout_stake and (
        hash_prevout_stake != '0000000000000000000000000000000000000000000000000000000000000000'
        or hash_prevout_n != 0xffffffff)

# nbits to target
def uint256_from_compact(bits):
    bitsN = (bits >> 24) & 0xff
    bitsBase = bits & 0xffffff
    target = bitsBase << (8 * (bitsN - 3))
    return target


# target to nbits
def compact_from_uint256(target):
    c = ("%064x" % target)[2:]
    while c[:2] == '00' and len(c) > 6:
        c = c[2:]
    bitsN, bitsBase = len(c) // 2, int('0x' + c[:6], 16)
    if bitsBase >= 0x800000:
        bitsN += 1
        bitsBase >>= 8
    new_bits = bitsN << 24 | bitsBase
    return new_bits


def recrypt_addr_to_bitcoin_addr(recrypt_addr):
    addr_type, hash160 = b58_address_to_hash160(recrypt_addr)
    if addr_type == ADDRTYPE_P2PKH:
        return hash160_to_b58_address(hash160, addrtype=BITCOIN_ADDRTYPE_P2PKH)
    elif addr_type == ADDRTYPE_P2SH:
        return hash160_to_b58_address(hash160, addr_type=BITCOIN_ADDRTYPE_P2SH)


def eth_abi_encode(abi, args):
    """
    >> abi = {"constant":True,"inputs":[{"name":"","type":"address"}],
"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"}
    >> eth_abi_encode(abi, ['9d3d4cc1986d81f9109f2b091b7732e7d9bcf63b'])
    >> '70a082310000000000000000000000009d3d4cc1986d81f9109f2b091b7732e7d9bcf63b'
    ## address must be lower case
    :param abi: dict
    :param args: list
    :return: str
    """
    if not abi:
        return "00"
    types = list([inp['type'] for inp in abi.get('inputs', [])])
    if abi.get('name'):
        result = function_abi_to_4byte_selector(abi) + encode_abi(types, args)
    else:
        result = encode_abi(types, args)
    return bh2u(result)
