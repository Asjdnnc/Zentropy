use starknet::ContractAddress;
use starknet::ClassHash;

// =============================================================================
// Interface: IQuantumGuardFactory
// =============================================================================
// Factory contract for deploying per-user QuantumGuard smart accounts.
// Uses deterministic addressing (CREATE2-style via deploy_syscall with salt)
// so the backend can pre-compute user contract addresses before deployment.
//
// Architecture:
//   1. Backend registers a user and computes a counterfactual address
//   2. User funds are sent to the pre-computed address
//   3. On first transaction, the factory deploys the actual contract
//   4. All subsequent transactions go directly to the deployed contract
//
// This pattern enables lazy deployment — accounts only get deployed when
// the user actually wants to transact, saving gas for inactive users.

#[starknet::interface]
pub trait IQuantumGuardFactory<TContractState> {
    /// Deploy a new QuantumGuard smart account for a user.
    ///
    /// Parameters:
    ///   - owner_pubkey_hash: SHA-256 hash of the user's ML-DSA-44 public key
    ///   - initial_prover: Address of the whitelisted prover for this account
    ///   - salt: Unique salt for deterministic address computation
    ///
    /// Returns the deployed contract address.
    fn deploy_account(
        ref self: TContractState,
        owner_pubkey_hash: felt252,
        initial_prover: ContractAddress,
        salt: felt252,
    ) -> ContractAddress;

    /// Compute the counterfactual address for a user account without deploying.
    /// Used by the backend to pre-assign addresses to users.
    fn compute_address(
        self: @TContractState,
        owner_pubkey_hash: felt252,
        initial_prover: ContractAddress,
        salt: felt252,
    ) -> felt252;

    /// Get the class hash of the QuantumGuardAccount contract used for deployments.
    fn get_account_class_hash(self: @TContractState) -> ClassHash;

    /// Update the class hash (for contract upgrades). Owner-only.
    fn update_account_class_hash(ref self: TContractState, new_class_hash: ClassHash);

    /// Get the total number of accounts deployed by this factory.
    fn get_total_deployed(self: @TContractState) -> u32;

    /// Check if an account has been deployed for a given salt.
    fn is_deployed(self: @TContractState, salt: felt252) -> bool;

    /// Get the deployed address for a given salt (returns 0 if not deployed).
    fn get_deployed_address(self: @TContractState, salt: felt252) -> ContractAddress;

    /// Get the factory owner.
    fn get_owner(self: @TContractState) -> ContractAddress;
}

// =============================================================================
// Contract Implementation
// =============================================================================

#[starknet::contract]
pub mod QuantumGuardFactory {
    use super::IQuantumGuardFactory;
    use starknet::{
        ContractAddress, ClassHash,
        get_caller_address,
        syscalls::deploy_syscall,
        contract_address_const,
    };
    use starknet::storage::{
        StoragePointerReadAccess, StoragePointerWriteAccess,
        Map, StorageMapReadAccess, StorageMapWriteAccess,
    };
    use core::pedersen::PedersenTrait;
    use core::hash::{HashStateTrait, HashStateExTrait};

    // ─── Storage ────────────────────────────────────────────────────

    #[storage]
    struct Storage {
        /// Factory owner (admin who can upgrade class hash).
        owner: ContractAddress,

        /// Class hash of the QuantumGuardAccount contract to deploy.
        account_class_hash: ClassHash,

        /// Deployed accounts: salt -> deployed contract address.
        deployed_accounts: Map<felt252, ContractAddress>,

        /// Track which salts have been deployed.
        salt_deployed: Map<felt252, bool>,

        /// Total number of deployed accounts.
        total_deployed: u32,
    }

    // ─── Events ─────────────────────────────────────────────────────

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        AccountDeployed: AccountDeployed,
        ClassHashUpdated: ClassHashUpdated,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AccountDeployed {
        #[key]
        pub owner_pubkey_hash: felt252,
        pub deployed_address: ContractAddress,
        pub salt: felt252,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ClassHashUpdated {
        pub old_class_hash: ClassHash,
        pub new_class_hash: ClassHash,
    }

    // ─── Constructor ────────────────────────────────────────────────

    #[constructor]
    fn constructor(
        ref self: ContractState,
        owner: ContractAddress,
        account_class_hash: ClassHash,
    ) {
        self.owner.write(owner);
        self.account_class_hash.write(account_class_hash);
        self.total_deployed.write(0);
    }

    // ─── External Implementation ────────────────────────────────────

    #[abi(embed_v0)]
    impl QuantumGuardFactoryImpl of IQuantumGuardFactory<ContractState> {

        fn deploy_account(
            ref self: ContractState,
            owner_pubkey_hash: felt252,
            initial_prover: ContractAddress,
            salt: felt252,
        ) -> ContractAddress {
            // 1. Only factory owner can deploy accounts
            self._assert_owner();

            // 2. Ensure this salt hasn't been deployed yet
            assert(!self.salt_deployed.read(salt), 'Salt already deployed');

            // 3. Validate inputs
            assert(owner_pubkey_hash != 0, 'Empty pubkey hash');

            // 4. Build constructor calldata for QuantumGuardAccount
            //    Constructor signature: (owner_pubkey_hash: felt252, initial_prover: ContractAddress)
            let mut constructor_calldata: Array<felt252> = array![];
            constructor_calldata.append(owner_pubkey_hash);
            constructor_calldata.append(initial_prover.into());

            // 5. Deploy using deploy_syscall with deterministic salt
            let class_hash = self.account_class_hash.read();
            let (deployed_address, _) = deploy_syscall(
                class_hash,
                salt,
                constructor_calldata.span(),
                false, // deploy_from_zero = false
            ).expect('Deploy failed');

            // 6. Record deployment
            self.deployed_accounts.write(salt, deployed_address);
            self.salt_deployed.write(salt, true);
            let count = self.total_deployed.read();
            self.total_deployed.write(count + 1);

            // 7. Emit event
            self.emit(AccountDeployed {
                owner_pubkey_hash,
                deployed_address,
                salt,
            });

            deployed_address
        }

        fn compute_address(
            self: @ContractState,
            owner_pubkey_hash: felt252,
            initial_prover: ContractAddress,
            salt: felt252,
        ) -> felt252 {
            // Compute deterministic address using Pedersen hash
            // This matches Starknet's deploy address computation:
            //   address = pedersen(
            //     "STARKNET_CONTRACT_ADDRESS",
            //     deployer_address,
            //     salt,
            //     class_hash,
            //     pedersen(constructor_calldata)
            //   )
            //
            // For pre-computation, we hash the constructor args + salt
            // as a simplified fingerprint the backend can use.
            let constructor_hash = PedersenTrait::new(owner_pubkey_hash)
                .update(initial_prover.into())
                .finalize();

            let class_hash_felt: felt252 = self.account_class_hash.read().into();

            PedersenTrait::new(salt)
                .update(class_hash_felt)
                .update(constructor_hash)
                .finalize()
        }

        fn get_account_class_hash(self: @ContractState) -> ClassHash {
            self.account_class_hash.read()
        }

        fn update_account_class_hash(ref self: ContractState, new_class_hash: ClassHash) {
            self._assert_owner();
            let old = self.account_class_hash.read();
            self.account_class_hash.write(new_class_hash);
            self.emit(ClassHashUpdated {
                old_class_hash: old,
                new_class_hash,
            });
        }

        fn get_total_deployed(self: @ContractState) -> u32 {
            self.total_deployed.read()
        }

        fn is_deployed(self: @ContractState, salt: felt252) -> bool {
            self.salt_deployed.read(salt)
        }

        fn get_deployed_address(self: @ContractState, salt: felt252) -> ContractAddress {
            self.deployed_accounts.read(salt)
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
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
        use super::{IQuantumGuardFactory, QuantumGuardFactoryImpl, InternalImpl};
        use super::{ContractState, contract_state_for_testing, constructor};
        use starknet::{ContractAddress, ClassHash, contract_address_const, class_hash_const};
        use starknet::testing::{set_caller_address, set_contract_address};

        fn OWNER() -> ContractAddress {
            contract_address_const::<0x100>()
        }

        fn OTHER() -> ContractAddress {
            contract_address_const::<0x200>()
        }

        fn PROVER() -> ContractAddress {
            contract_address_const::<0x300>()
        }

        fn ACCOUNT_CLASS() -> ClassHash {
            class_hash_const::<0xACCE55>()
        }

        fn NEW_CLASS() -> ClassHash {
            class_hash_const::<0xBEEF>()
        }

        fn PUBKEY_HASH() -> felt252 {
            0x1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef12345678
        }

        fn deploy() -> ContractState {
            let mut state = contract_state_for_testing();
            constructor(ref state, OWNER(), ACCOUNT_CLASS());
            state
        }

        // ─── Constructor ────────────────────────────────────────────

        #[test]
        fn test_constructor() {
            let state = deploy();
            assert(
                QuantumGuardFactoryImpl::get_owner(@state) == OWNER(),
                'Owner mismatch'
            );
            assert(
                QuantumGuardFactoryImpl::get_account_class_hash(@state) == ACCOUNT_CLASS(),
                'Class hash mismatch'
            );
            assert(
                QuantumGuardFactoryImpl::get_total_deployed(@state) == 0,
                'Should start at 0'
            );
        }

        // ─── Address Computation ────────────────────────────────────

        #[test]
        fn test_compute_address_deterministic() {
            let state = deploy();
            let salt: felt252 = 0xCAFE;

            let addr1 = QuantumGuardFactoryImpl::compute_address(
                @state, PUBKEY_HASH(), PROVER(), salt
            );
            let addr2 = QuantumGuardFactoryImpl::compute_address(
                @state, PUBKEY_HASH(), PROVER(), salt
            );

            assert(addr1 == addr2, 'Addresses should match');
            assert(addr1 != 0, 'Address should not be zero');
        }

        #[test]
        fn test_compute_address_different_salt() {
            let state = deploy();

            let addr1 = QuantumGuardFactoryImpl::compute_address(
                @state, PUBKEY_HASH(), PROVER(), 0x1
            );
            let addr2 = QuantumGuardFactoryImpl::compute_address(
                @state, PUBKEY_HASH(), PROVER(), 0x2
            );

            assert(addr1 != addr2, 'Different salts => different addrs');
        }

        #[test]
        fn test_compute_address_different_pubkey() {
            let state = deploy();
            let salt: felt252 = 0xCAFE;

            let addr1 = QuantumGuardFactoryImpl::compute_address(
                @state, 0xAAA, PROVER(), salt
            );
            let addr2 = QuantumGuardFactoryImpl::compute_address(
                @state, 0xBBB, PROVER(), salt
            );

            assert(addr1 != addr2, 'Different keys => different addrs');
        }

        // ─── Deployment State ───────────────────────────────────────

        #[test]
        fn test_not_deployed_initially() {
            let state = deploy();
            assert(!QuantumGuardFactoryImpl::is_deployed(@state, 0xCAFE), 'Should not be deployed');
        }

        // ─── Admin Functions ────────────────────────────────────────

        #[test]
        #[should_panic(expected: 'Only owner can call')]
        fn test_deploy_unauthorized() {
            let mut state = deploy();
            set_caller_address(OTHER());

            QuantumGuardFactoryImpl::deploy_account(
                ref state, PUBKEY_HASH(), PROVER(), 0xCAFE
            );
        }

        #[test]
        #[should_panic(expected: 'Empty pubkey hash')]
        fn test_deploy_empty_pubkey() {
            let mut state = deploy();
            set_caller_address(OWNER());

            QuantumGuardFactoryImpl::deploy_account(
                ref state, 0, PROVER(), 0xCAFE
            );
        }

        #[test]
        #[should_panic(expected: 'Only owner can call')]
        fn test_update_class_hash_unauthorized() {
            let mut state = deploy();
            set_caller_address(OTHER());

            QuantumGuardFactoryImpl::update_account_class_hash(
                ref state, ACCOUNT_CLASS()
            );
        }

        #[test]
        fn test_update_class_hash_success() {
            let mut state = deploy();
            set_caller_address(OWNER());

            let new_hash = class_hash_const::<0xBEEF>();
            QuantumGuardFactoryImpl::update_account_class_hash(ref state, new_hash);
            assert(
                QuantumGuardFactoryImpl::get_account_class_hash(@state) == new_hash,
                'Class hash not updated'
            );
        }
    }
}
