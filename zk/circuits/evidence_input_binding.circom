pragma circom 2.2.3;

include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/poseidon.circom";

// Proves knowledge of the complete ordered leaf set that creates `root`, then
// binds that root and count to independently verified prompt/request digests.
// SHA-256 and PromptBuild are verified outside the circuit from disclosed data.
template EvidenceInputBinding() {
    signal input root;
    signal input documentCount;
    signal input promptHashHi;
    signal input promptHashLo;
    signal input requestHashHi;
    signal input requestHashLo;
    signal input inputBinding;
    signal input leaves[16];

    // SHA256 domain strings reduced modulo the BN254 scalar field.
    var NODE_DOMAIN = 8557462712775812514539279517506295791093801082275788230420586124346560037251;
    var PADDING_LEAF = 7887870799067887111898770426225253091062412173836339915293018532855330290766;
    var INPUT_BINDING_DOMAIN = 12163706072698444783980021892400976631680021346937526568172547568961433304363;

    component countValid = LessThan(5);
    countValid.in[0] <== documentCount;
    countValid.in[1] <== 11;
    countValid.out === 1;

    signal treeLeaves[16];
    component active[16];
    for (var i = 0; i < 16; i++) {
        active[i] = LessThan(5);
        active[i].in[0] <== i;
        active[i].in[1] <== documentCount;
        // Inactive witness positions are fixed to zero; the tree receives the
        // public protocol padding leaf instead.
        leaves[i] * (1 - active[i].out) === 0;
        treeLeaves[i] <== active[i].out * leaves[i] + (1 - active[i].out) * PADDING_LEAF;
    }

    component level1[8];
    signal nodes1[8];
    for (var j = 0; j < 8; j++) {
        level1[j] = Poseidon(3);
        level1[j].inputs[0] <== NODE_DOMAIN;
        level1[j].inputs[1] <== treeLeaves[2*j];
        level1[j].inputs[2] <== treeLeaves[2*j+1];
        nodes1[j] <== level1[j].out;
    }

    component level2[4];
    signal nodes2[4];
    for (var k = 0; k < 4; k++) {
        level2[k] = Poseidon(3);
        level2[k].inputs[0] <== NODE_DOMAIN;
        level2[k].inputs[1] <== nodes1[2*k];
        level2[k].inputs[2] <== nodes1[2*k+1];
        nodes2[k] <== level2[k].out;
    }

    component level3[2];
    signal nodes3[2];
    for (var m = 0; m < 2; m++) {
        level3[m] = Poseidon(3);
        level3[m].inputs[0] <== NODE_DOMAIN;
        level3[m].inputs[1] <== nodes2[2*m];
        level3[m].inputs[2] <== nodes2[2*m+1];
        nodes3[m] <== level3[m].out;
    }

    component level4 = Poseidon(3);
    level4.inputs[0] <== NODE_DOMAIN;
    level4.inputs[1] <== nodes3[0];
    level4.inputs[2] <== nodes3[1];
    root === level4.out;

    component bindRoot = Poseidon(3);
    bindRoot.inputs[0] <== INPUT_BINDING_DOMAIN;
    bindRoot.inputs[1] <== root;
    bindRoot.inputs[2] <== documentCount;
    component bindPrompt = Poseidon(3);
    bindPrompt.inputs[0] <== bindRoot.out;
    bindPrompt.inputs[1] <== promptHashHi;
    bindPrompt.inputs[2] <== promptHashLo;
    component bindRequest = Poseidon(3);
    bindRequest.inputs[0] <== bindPrompt.out;
    bindRequest.inputs[1] <== requestHashHi;
    bindRequest.inputs[2] <== requestHashLo;
    inputBinding === bindRequest.out;
}

component main {public [root, documentCount, promptHashHi, promptHashLo, requestHashHi, requestHashLo, inputBinding]} = EvidenceInputBinding();
