pragma circom 2.2.3;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/poseidon.circom";

// Proves that `leaf` occurs at `index` in a fixed-height (16-leaf) tree.
// The evidence-to-leaf SHA-256/Poseidon transformation is intentionally kept
// outside this circuit; `leaf`, `root`, and `index` are public, while the
// Merkle authentication path stays private.
template EvidenceMembership() {
    signal input root;
    signal input leaf;
    signal input index;
    signal input siblings[4];

    // SHA256("zkrag:node:v1") reduced modulo the BN254 scalar field.
    var NODE_DOMAIN = 8557462712775812514539279517506295791093801082275788230420586124346560037251;

    component indexBits = Num2Bits(4);
    indexBits.in <== index;

    signal current[5];
    signal left[4];
    signal right[4];
    component hashes[4];

    current[0] <== leaf;
    for (var level = 0; level < 4; level++) {
        // bit=0: current is left; bit=1: current is right.
        left[level] <== current[level] + indexBits.out[level] * (siblings[level] - current[level]);
        right[level] <== siblings[level] + indexBits.out[level] * (current[level] - siblings[level]);

        hashes[level] = Poseidon(3);
        hashes[level].inputs[0] <== NODE_DOMAIN;
        hashes[level].inputs[1] <== left[level];
        hashes[level].inputs[2] <== right[level];
        current[level + 1] <== hashes[level].out;
    }

    root === current[4];
}

component main {public [root, leaf, index]} = EvidenceMembership();
