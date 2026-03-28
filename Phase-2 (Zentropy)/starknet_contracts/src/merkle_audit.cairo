use starknet::ContractAddress;

// =============================================================================
// Interface: IMerkleAudit
// =============================================================================
// On-chain Merkle audit trail for transaction batches.
// The backend periodically commits Merkle roots of transaction batches.
// Anyone can verify a transaction is included by providing a Merkle proof.

#[starknet::interface]
pub trait IMerkleAudit<TContractState> {
    /// Commit a Merkle root for a batch of transactions.
    /// Only callable by an approved committer (the batch_committer service).
    fn commit_merkle_batch(
        ref self: TContractState,
        batch_id: felt252,
        merkle_root: felt252,
        tx_count: u32,
    );

    /// Verify that a transaction hash is included in a committed batch
    /// by checking its Merkle proof on-chain.
    ///
    /// Parameters:
    ///   - batch_id: The batch to verify against
    ///   - leaf_hash: SHA-256 hash of the transaction data
    ///   - proof: Array of sibling hashes along the Merkle path
    ///   - leaf_index: Position of the leaf in the tree
    ///
    /// Returns true if the proof is valid.
    fn verify_transaction_in_batch(
        self: @TContractState,
        batch_id: felt252,
        leaf_hash: felt252,
        proof: Array<felt252>,
        leaf_index: u32,
    ) -> bool;

    /// Get the stored Merkle root for a batch.
    fn get_batch_root(self: @TContractState, batch_id: felt252) -> felt252;

    /// Get the transaction count for a batch.
    fn get_batch_tx_count(self: @TContractState, batch_id: felt252) -> u32;

    /// Get the total number of committed batches.
    fn get_total_batches(self: @TContractState) -> u32;

    /// Check if an address is an approved committer.
    fn is_approved_committer(self: @TContractState, addr: ContractAddress) -> bool;

    /// Add an approved committer (owner-only via self-call).
    fn add_committer(ref self: TContractState, addr: ContractAddress);

    /// Remove an approved committer (owner-only via self-call).
    fn remove_committer(ref self: TContractState, addr: ContractAddress);
}

// =============================================================================
// Contract Implementation
// =============================================================================

#[starknet::contract]
pub mod MerkleAuditTrail {
    use super::IMerkleAudit;
    use starknet::{ContractAddress, get_caller_address, get_contract_address};
    use starknet::storage::{
        StoragePointerReadAccess, StoragePointerWriteAccess,
        Map, StorageMapReadAccess, StorageMapWriteAccess,
    };
    use core::pedersen::PedersenTrait;
    use core::hash::{HashStateTrait, HashStateExTrait};

    // ─── Storage ────────────────────────────────────────────────────

    #[storage]
    struct Storage {
        /// Owner address (the QuantumGuard account or deployer).
        owner: ContractAddress,

        /// Committed Merkle roots: batch_id -> merkle_root
        batch_roots: Map<felt252, felt252>,

        /// Batch transaction counts: batch_id -> tx_count
        batch_tx_counts: Map<felt252, u32>,

        /// Batch commit timestamps: batch_id -> block_timestamp
        batch_timestamps: Map<felt252, u64>,

        /// Total number of committed batches.
        total_batches: u32,

        /// Approved committer addresses (batch committer service wallets).
        approved_committers: Map<ContractAddress, bool>,
    }

    // ─── Events ─────────────────────────────────────────────────────

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        BatchCommitted: BatchCommitted,
        TransactionVerified: TransactionVerified,
        CommitterAdded: CommitterAdded,
        CommitterRemoved: CommitterRemoved,
    }

    #[derive(Drop, starknet::Event)]
    pub struct BatchCommitted {
        #[key]
        pub batch_id: felt252,
        pub merkle_root: felt252,
        pub tx_count: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct TransactionVerified {
        #[key]
        pub batch_id: felt252,
        pub leaf_hash: felt252,
        pub leaf_index: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CommitterAdded {
        #[key]
        pub addr: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct CommitterRemoved {
        #[key]
        pub addr: ContractAddress,
    }

    // ─── Constructor ────────────────────────────────────────────────

    #[constructor]
    fn constructor(
        ref self: ContractState,
        owner: ContractAddress,
        initial_committer: ContractAddress,
    ) {
        self.owner.write(owner);
        self.approved_committers.write(initial_committer, true);
        self.total_batches.write(0);
    }

    // ─── External Implementation ────────────────────────────────────

    #[abi(embed_v0)]
    impl MerkleAuditImpl of IMerkleAudit<ContractState> {

        fn commit_merkle_batch(
            ref self: ContractState,
            batch_id: felt252,
            merkle_root: felt252,
            tx_count: u32,
        ) {
            // Verify caller is an approved committer
            let caller = get_caller_address();
            assert(self.approved_committers.read(caller), 'Not approved committer');

            // Ensure batch hasn't been committed yet
            let existing = self.batch_roots.read(batch_id);
            assert(existing == 0, 'Batch already committed');

            // Ensure non-empty root
            assert(merkle_root != 0, 'Empty merkle root');
            assert(tx_count > 0, 'Empty batch');

            // Store batch data
            self.batch_roots.write(batch_id, merkle_root);
            self.batch_tx_counts.write(batch_id, tx_count);

            // Increment total batches
            let count = self.total_batches.read();
            self.total_batches.write(count + 1);

            // Emit event
            self.emit(BatchCommitted {
                batch_id,
                merkle_root,
                tx_count,
            });
        }

        fn verify_transaction_in_batch(
            self: @ContractState,
            batch_id: felt252,
            leaf_hash: felt252,
            proof: Array<felt252>,
            leaf_index: u32,
        ) -> bool {
            // Get stored root
            let stored_root = self.batch_roots.read(batch_id);
            if stored_root == 0 {
                return false; // Batch not committed
            }

            // Compute Merkle root from proof
            // Walk up the tree, combining hashes using Pedersen hash
            let mut current = leaf_hash;
            let mut index = leaf_index;
            let proof_span = proof.span();
            let mut i: u32 = 0;

            loop {
                if i >= proof_span.len() {
                    break;
                }

                let sibling = *proof_span.at(i);

                // If index is even, current is left child; if odd, current is right child
                if index % 2 == 0 {
                    // current || sibling
                    current = PedersenTrait::new(current).update(sibling).finalize();
                } else {
                    // sibling || current
                    current = PedersenTrait::new(sibling).update(current).finalize();
                };

                index = index / 2;
                i += 1;
            };

            // Check if computed root matches stored root
            let is_valid = current == stored_root;

            if is_valid {
                // Note: we can't emit in a view function in production,
                // but for audit trail purposes we track verification attempts
                // via the return value
            }

            is_valid
        }

        fn get_batch_root(self: @ContractState, batch_id: felt252) -> felt252 {
            self.batch_roots.read(batch_id)
        }

        fn get_batch_tx_count(self: @ContractState, batch_id: felt252) -> u32 {
            self.batch_tx_counts.read(batch_id)
        }

        fn get_total_batches(self: @ContractState) -> u32 {
            self.total_batches.read()
        }

        fn is_approved_committer(self: @ContractState, addr: ContractAddress) -> bool {
            self.approved_committers.read(addr)
        }

        fn add_committer(ref self: ContractState, addr: ContractAddress) {
            self._assert_owner();
            self.approved_committers.write(addr, true);
            self.emit(CommitterAdded { addr });
        }

        fn remove_committer(ref self: ContractState, addr: ContractAddress) {
            self._assert_owner();
            self.approved_committers.write(addr, false);
            self.emit(CommitterRemoved { addr });
        }
    }

    // ─── Internal helpers ───────────────────────────────────────────

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        fn _assert_owner(self: @ContractState) {
            let caller = get_caller_address();
            let owner = self.owner.read();
            assert(caller == owner, 'Only owner can call');
        }
    }

    // =============================================================================
    // Unit Tests
    // =============================================================================

    #[cfg(test)]
    mod tests {
        use super::{IMerkleAudit, MerkleAuditImpl, InternalImpl};
        use super::{ContractState, contract_state_for_testing, constructor};
        use starknet::{ContractAddress, contract_address_const};
        use starknet::testing::{set_caller_address, set_contract_address};
        use core::pedersen::PedersenTrait;
        use core::hash::{HashStateTrait, HashStateExTrait};

        fn OWNER() -> ContractAddress {
            contract_address_const::<0x100>()
        }

        fn COMMITTER() -> ContractAddress {
            contract_address_const::<0x200>()
        }

        fn OTHER() -> ContractAddress {
            contract_address_const::<0x300>()
        }

        fn deploy() -> ContractState {
            let mut state = contract_state_for_testing();
            constructor(ref state, OWNER(), COMMITTER());
            state
        }

        // ─── Constructor ────────────────────────────────────────────

        #[test]
        fn test_constructor_initial_state() {
            let state = deploy();
            assert(MerkleAuditImpl::get_total_batches(@state) == 0, 'Should start at 0');
            assert(MerkleAuditImpl::is_approved_committer(@state, COMMITTER()), 'Committer not set');
            assert(!MerkleAuditImpl::is_approved_committer(@state, OTHER()), 'Other should not be committer');
        }

        // ─── Commit Batch ───────────────────────────────────────────

        #[test]
        fn test_commit_batch_success() {
            let mut state = deploy();
            set_caller_address(COMMITTER());

            let batch_id: felt252 = 0x1;
            let merkle_root: felt252 = 0xabcdef123456;
            let tx_count: u32 = 10;

            MerkleAuditImpl::commit_merkle_batch(ref state, batch_id, merkle_root, tx_count);

            assert(MerkleAuditImpl::get_batch_root(@state, batch_id) == merkle_root, 'Root mismatch');
            assert(MerkleAuditImpl::get_batch_tx_count(@state, batch_id) == tx_count, 'Count mismatch');
            assert(MerkleAuditImpl::get_total_batches(@state) == 1, 'Total should be 1');
        }

        #[test]
        #[should_panic(expected: 'Not approved committer')]
        fn test_commit_batch_unauthorized() {
            let mut state = deploy();
            set_caller_address(OTHER());

            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, 0xabc, 5);
        }

        #[test]
        #[should_panic(expected: 'Batch already committed')]
        fn test_cannot_recommit_batch() {
            let mut state = deploy();
            set_caller_address(COMMITTER());

            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, 0xabc, 5);
            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, 0xdef, 3);
        }

        #[test]
        #[should_panic(expected: 'Empty merkle root')]
        fn test_reject_empty_root() {
            let mut state = deploy();
            set_caller_address(COMMITTER());

            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, 0, 5);
        }

        #[test]
        #[should_panic(expected: 'Empty batch')]
        fn test_reject_zero_count() {
            let mut state = deploy();
            set_caller_address(COMMITTER());

            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, 0xabc, 0);
        }

        // ─── Verify Proof ───────────────────────────────────────────

        #[test]
        fn test_verify_proof_simple() {
            // Build a simple 2-leaf tree:
            // leaf0 = 0x111, leaf1 = 0x222
            // root = Pedersen(leaf0, leaf1)
            let leaf0: felt252 = 0x111;
            let leaf1: felt252 = 0x222;
            let root = PedersenTrait::new(leaf0).update(leaf1).finalize();

            let mut state = deploy();
            set_caller_address(COMMITTER());
            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, root, 2);

            // Verify leaf0 (index=0, proof=[leaf1])
            let valid = MerkleAuditImpl::verify_transaction_in_batch(
                @state, 0x1, leaf0, array![leaf1], 0,
            );
            assert(valid, 'Leaf0 proof failed');

            // Verify leaf1 (index=1, proof=[leaf0])
            let valid2 = MerkleAuditImpl::verify_transaction_in_batch(
                @state, 0x1, leaf1, array![leaf0], 1,
            );
            assert(valid2, 'Leaf1 proof failed');
        }

        #[test]
        fn test_verify_invalid_proof() {
            let leaf0: felt252 = 0x111;
            let leaf1: felt252 = 0x222;
            let root = PedersenTrait::new(leaf0).update(leaf1).finalize();

            let mut state = deploy();
            set_caller_address(COMMITTER());
            MerkleAuditImpl::commit_merkle_batch(ref state, 0x1, root, 2);

            // Wrong proof
            let valid = MerkleAuditImpl::verify_transaction_in_batch(
                @state, 0x1, leaf0, array![0xbad], 0,
            );
            assert(!valid, 'Should reject bad proof');
        }

        #[test]
        fn test_verify_nonexistent_batch() {
            let state = deploy();

            let valid = MerkleAuditImpl::verify_transaction_in_batch(
                @state, 0x999, 0x111, array![0x222], 0,
            );
            assert(!valid, 'Should reject missing batch');
        }

        // ─── Admin ──────────────────────────────────────────────────

        #[test]
        fn test_add_committer() {
            let mut state = deploy();
            set_caller_address(OWNER());

            MerkleAuditImpl::add_committer(ref state, OTHER());
            assert(MerkleAuditImpl::is_approved_committer(@state, OTHER()), 'Not added');
        }

        #[test]
        #[should_panic(expected: 'Only owner can call')]
        fn test_add_committer_unauthorized() {
            let mut state = deploy();
            set_caller_address(OTHER());

            MerkleAuditImpl::add_committer(ref state, OTHER());
        }

        #[test]
        fn test_remove_committer() {
            let mut state = deploy();
            set_caller_address(OWNER());

            MerkleAuditImpl::remove_committer(ref state, COMMITTER());
            assert(!MerkleAuditImpl::is_approved_committer(@state, COMMITTER()), 'Not removed');
        }
    }
}
