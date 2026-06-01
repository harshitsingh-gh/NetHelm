# """First Batfish query against frr_square snapshot.

# Validates: snapshot loads, all four nodes are recognized, BGP RIB has the
# four /32 loopbacks, eBGP/iBGP topology matches the lab.
# """
# from pathlib import Path
# import pandas as pd
# from pybatfish.client.session import Session

# SNAPSHOT_DIR = Path(__file__).parent / "snapshot"
# NETWORK = "frrsq"
# SNAPSHOT = "v1_2026-05-27"

# bf = Session(host="127.0.0.1")
# bf.set_network(NETWORK)
# bf.init_snapshot(str(SNAPSHOT_DIR), name=SNAPSHOT, overwrite=True)

# print("\n== nodes ==")
# #print(bf.q.nodeProperties().answer().frame()[
# #    ["Node", "Configuration_Format", "Routing_Protocols"]
# #])

# nodes_df = bf.q.nodeProperties().answer().frame()
# cols = [c for c in ["Node", "Configuration_Format", "Routing_Policies"] if c in nodes_df.columns]
# print(nodes_df[cols])

# print("\n== bgp peer config ==")
# print(bf.q.bgpPeerConfiguration().answer().frame())

# print("\n== bgp session status ==")
# print(bf.q.bgpSessionStatus().answer().frame())

# print("\n== bgp RIB on r1 ==")
# rib = bf.q.bgpRib(nodes="r1").answer().frame()
# print(rib[["Node", "VRF", "Network", "Next_Hop_IP", "AS_Path"]])

# # print("\n== reachability r1 lo -> r3 lo ==")
# # trace = bf.q.traceroute(
# #     startLocation="@enter(r1[lo])", headers={"dstIps": "10.0.0.3"}
# # ).answer().frame()
# # print(trace)

# print("\n== reachability r1 lo -> r3 lo ==")
# trace = bf.q.traceroute(
#     startLocation="r1", headers={"dstIps": "10.0.0.3", "srcIps": "10.0.0.1"}
# ).answer().frame()
# print(trace)

from pathlib import Path
from pybatfish.client.session import Session

SNAPSHOT_DIR = Path(__file__).parent / "snapshot"
NETWORK = "frrsq"
SNAPSHOT = "v1_2026-05-27"

bf = Session(host="127.0.0.1")
bf.set_network(NETWORK)
bf.init_snapshot(str(SNAPSHOT_DIR), name=SNAPSHOT, overwrite=True)

print("\n== parse status ==")
parse = bf.q.fileParseStatus().answer().frame()
print(parse[["File_Name", "Status", "File_Format", "Nodes"]].to_string())

failed = parse[parse["Status"] != "PASSED"]
if not failed.empty:
    raise SystemExit("ERROR: snapshot parse failed")

print("\n== init issues ==")
issues = bf.q.initIssues().answer().frame()
print(issues.to_string())
if not issues.empty:
    raise SystemExit("ERROR: snapshot has init issues")

print("\n== nodes ==")
nodes = bf.q.nodeProperties().answer().frame()
print(nodes[["Node", "Configuration_Format", "Interfaces", "VRFs"]].to_string())

print("\n== bgp peer config ==")
print(bf.q.bgpPeerConfiguration().answer().frame().to_string())

print("\n== bgp session status ==")
sessions = bf.q.bgpSessionStatus().answer().frame()
print(sessions.to_string())

bad_sessions = sessions[sessions["Established_Status"] != "ESTABLISHED"]
if not bad_sessions.empty:
    raise SystemExit("ERROR: some BGP sessions are not established")

print("\n== routes on r1 ==")
routes = bf.q.routes(nodes="r1").answer().frame()
print(routes.to_string())

print("\n== bgp RIB on r1 ==")
rib = bf.q.bgpRib(nodes="r1").answer().frame()
print(rib.to_string())

print("\n== traceroute r1 lo -> r3 lo ==")
trace = bf.q.traceroute(
    startLocation="@enter(r1[lo])",
    headers={"srcIps": "10.0.0.1", "dstIps": "10.0.0.3"},
).answer().frame()
print(trace.to_string())