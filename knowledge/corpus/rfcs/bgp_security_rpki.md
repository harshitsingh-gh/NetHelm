# BGP Security: RPKI, Route Leaks, and Hijack Prevention

## The Core BGP Security Problem
BGP has no built-in authentication of routing information. Any AS can announce any prefix. The only enforcement is:
1. Social/operational agreements (IRR, peering contracts)
2. Manual route filters (tedious, often incomplete)
3. Cryptographic attestation (RPKI — the modern solution)

## Route Hijack vs. Route Leak (RFC 7908)
**Route Hijack**: Unauthorized announcement of a prefix by an AS that does not own it.
- Example: Pakistan Telecom announcing YouTube's 208.65.153.0/24 (2008)
- Typically involves a more-specific prefix (longest-prefix-match wins)
- Can be accidental or malicious

**Route Leak**: A prefix learned from one AS is re-advertised to another AS in violation of routing policy.
- Example: Telekom Malaysia re-advertising Level3 routes back to Level3 (2015)
- Does not involve unauthorized prefix ownership — the origin AS legitimately owns the prefix
- Violates the intended "valley-free" routing model

**RFC 7908 Leak Types**:
1. Type 1: Full table leaked to transit provider (Telekom Malaysia 2015 pattern)
2. Type 2: More-specific leaked to transit (Pakistan Telecom 2008 pattern)
3. Type 3: Provider leaked to sibling (lateral peering leak)
4. Type 4: Internal routes leaked to provider (ISP internal prefixes exposed)
5. Type 5: Provider routes leaked back upstream (hairpin leak)
6. Type 6: IBGP prefix leaked to eBGP (no-export community ignored)

## RPKI (Resource Public Key Infrastructure)

### Architecture
- **RIR (ARIN, RIPE, APNIC, LACNIC, AFRINIC)** issue ROAs (Route Origin Authorizations)
- ROA contains: prefix, max-prefix-length, origin AS number
- Signed by the prefix owner's private key
- Published to RPKI repositories (rsync/RRDP)

### ROA Example
```
Prefix: 192.0.2.0/24
Max-Length: /24
Origin AS: 64496
```
This ROA says: AS64496 is authorized to announce 192.0.2.0/24 or any more-specific up to /24.

### Route Origin Validation (ROV)
BGP routers query a local RPKI cache (rtrsync/Routinator/FORT) and validate incoming routes:
- **VALID**: prefix is covered by a ROA matching the origin AS
- **INVALID**: prefix covered by a ROA but origin AS doesn't match, or prefix length exceeds maxLength
- **NOT_FOUND**: no ROA covers this prefix

**Recommended policy**:
- Drop INVALID routes (prevents hijacks and most route leaks)
- Prefer VALID over NOT_FOUND
- Accept NOT_FOUND (dropping all NOT_FOUND would break most of the Internet)

### RPKI Deployment Status (circa 2024)
- ~50% of global prefixes have ROAs
- ~30% of transit ASes perform ROV
- Major operators doing ROV: AT&T, Comcast, Cloudflare, ARIN RPKI mandated for ARIN customers
- Pakistan/YouTube 2008: would be blocked by ROV (invalid origin AS)
- Telekom Malaysia 2015: partially blocked (some leaked prefixes would be VALID — TM itself had ROAs for some customer space)

## BGP OTC (Only to Customer) — RFC 9234
Addresses route leaks that RPKI doesn't prevent (RPKI validates origin, not path).

**BGP Role attribute**: Tags a session as customer/provider/peer/rs/rs-client
- When a router receives a route tagged with OTC from a provider/peer: it must not re-advertise to another provider/peer
- Prevents Type 1 leak (full table leak to transit)

**FRR support**: As of FRR 8.x, BGP Role attribute is supported.

## AS_PATH Verification (BGPsec — RFC 8205)
BGPsec provides cryptographic signing of the AS_PATH, preventing AS_PATH manipulation.

**Current status**: Not widely deployed. Requires PKI per-AS and per-hop signing — high operational overhead.
**Practical alternative**: Prefix-list + AS_PATH ACL filters at peering points.

## IRR (Internet Routing Registry)

### How It Works
ASes register their routing policies in public IRR databases (ARIN, RIPE, RADB, etc.):
```
route: 192.0.2.0/24
origin: AS64496
```

Route filters are generated from IRR data using tools like bgpq4 or IRRToolSet.

### Limitations
- Not authenticated (anyone can register anything in some IRRs)
- Often stale (operators forget to update when changing providers)
- Not all ASes register their routes
- IRR-generated filters require regular regeneration as the Internet changes

### IRRDB (IRR Database) Filter Generation (Cisco Example)
```bash
# Generate prefix-list from IRR for AS64496:
bgpq4 -4 -l PEER_64496_PREFIXES AS64496
```
Generates:
```
ip prefix-list PEER_64496_PREFIXES seq 10 permit 192.0.2.0/24
ip prefix-list PEER_64496_PREFIXES seq 20 deny 0.0.0.0/0 le 32
```

## MANRS (Mutually Agreed Norms for Routing Security)
Industry initiative requiring participating networks to:
1. Prevent propagation of incorrect routing information
2. Prevent traffic with spoofed source IP addresses
3. Facilitate global operational communication and coordination
4. Facilitate validation of routing information

MANRS membership is a soft signal of routing hygiene.

## Blast Radius of BGP Security Failures

| Attack Type | D1 | D2 | D3 | D4 | D7 | Prevention |
|---|---|---|---|---|---|---|
| Prefix hijack (exact match) | 0 | 0 | 100% (traffic goes to attacker) | ✓ | ✓ | RPKI ROV |
| Prefix hijack (more-specific) | 0 | 0 | Partial (more-specific wins) | ✓ | ✓ | RPKI ROV |
| Route leak (full table) | 0 | 0 | Partial (congestion) | ✓ | ✓ | OTC, IRR |
| AS_PATH manipulation | 0 | 0 | Variable | ✓ | ✓ | BGPsec |
| Session hijack (MITM) | Potential | Potential | Total | | | TCP-AO (RFC 5925) |

## TCP MD5 / TCP Authentication Option (for BGP Session Security)
BGP sessions protected with TCP MD5 (RFC 2385) or TCP-AO (RFC 5925) to prevent:
- Session injection (fake BGP UPDATE/NOTIFICATION packets)
- Session teardown (forged NOTIFICATION with RST)

**MD5 config (IOS)**: `neighbor X.X.X.X password <key>`
**TCP-AO** (newer, stronger): not universally deployed yet

## NetHELM Scenario Design Guidance
For blast-radius scenarios involving BGP security:
- Hijack scenarios: model as "a new more-specific announcement appears" — check D4 (waypoint) and D7 (forwarding) not D1/D2
- Route leak: model as "a route learned from ISP_A is now advertised to ISP_B" — check D4/D7; BGP sessions remain ESTABLISHED
- RPKI INVALID: model as "route origin AS doesn't match ROA" — platforms doing ROV will drop the route; platforms not doing ROV will accept it
