#!/usr/bin/env python2
# Copyright (c) 2014 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import *
from test_framework.mininode import *
from test_framework.script import *
from pprint import pprint
from time import sleep
from io import BytesIO

# Upgrade some coins to be in v2 outputs and then spend them
class RawTransactionsTest(BitcoinTestFramework):

    def setup_chain(self):
        print("Initializing test directory "+self.options.tmpdir)
        initialize_chain_clean(self.options.tmpdir, 2)

    def setup_network(self, split=False):
        self.nodes = start_nodes(2, self.options.tmpdir)

        connect_nodes_bi(self.nodes,0,1)

        self.is_network_split=False
        self.sync_all()

    def run_test(self):
        print "Mining blocks..."
        self.nodes[0].generate(120)
        self.sync_all()

        # Node 0 sends 5 coins via v2 tx to node 1, the output is going to be
        # annotated with its normalized hash so we can later use it.
        addr1 = self.nodes[1].getnewaddress()
        inputs = []
        outputs = {addr1: 5}
        tx0 = self.nodes[0].createrawtransaction(inputs, outputs)

        # Now disect this transaction so we can fix the output script to use OP_CHECKSIGEX

        t = CTransaction()
        t.deserialize(BytesIO(tx0.decode('hex')))
        t.nVersion = 2

        # Replace the pay-to-pubkeyhash with the equivalent OP_CHECKSIGEX 
        # Trim off the OP_CHECKSIG, push OP_CHECKSIGEX and its OP_4 parameter,
        # i.e., singlesig, no verify and normalize.
        spk = t.vout[0].scriptPubKey[:-1] + chr(int(OP_4)) + chr(int(OP_CHECKSIGEX))
        t.vout[0].scriptPubKey = spk
        raw = t.serialize().encode('hex')

        # Now add funds, done here because it randomizes outputs
        res = self.nodes[0].fundrawtransaction(raw)
        out_pos = 1 - res['changepos']
        funded_tx = res['hex']

        # Getting this signed should work trivially
        res = self.nodes[0].signrawtransaction(funded_tx)
        assert(res['complete'])

        # Ready to add the v2 OP_CHECKSIGEX output to the UTXO
        legacy_txid = self.nodes[0].sendrawtransaction(res['hex'])
        self.sync_all()

        # Mine it and check the tx gets confirmed
        b = self.nodes[0].generate(1)[0]
        self.sync_all()
        assert(legacy_txid in self.nodes[0].getblock(b)['tx'])
        out = self.nodes[0].gettxout(legacy_txid, out_pos)
        assert_equal(out['scriptPubKey']['hex'], spk.encode('hex'))

        ####
        # PART II: Spending the OP_CHECKSIGEX outputs
        ####
        # The bitcoin core client takes care of fishing the normalized
        # transaction ID out of its UTXO so we just reference the prevout
        # normally here
        output = {'txid': legacy_txid, 'vout': out_pos, 'scriptPubKey': spk.encode('hex')}
        addr0 = self.nodes[0].getnewaddress()

        # Force the use of the normalized output and allow for some fees
        tx1 = self.nodes[1].createrawtransaction([output], {addr0: 4.999})
        tx1 = '02' + tx1[2:]  # Patch version to be v2
        signed_tx = self.nodes[1].signrawtransaction(tx1)
        assert(signed_tx['complete'])
        spending_legacy_id = self.nodes[1].sendrawtransaction(signed_tx['hex'])

        # Finally mine a block and see if the tx gets confirmed
        b = self.nodes[1].generate(1)[0]
        #self.sync_all()
        #assert(spending_legacy_id in self.nodes[1].getblock[b]['tx'])
        
        # Assert that the recipient recognizes the output as its own
        #assert(spending_legacy_id in [i['txid'] for i in self.nodes[0].listunspent()])


if __name__ == '__main__':
    RawTransactionsTest().main()
