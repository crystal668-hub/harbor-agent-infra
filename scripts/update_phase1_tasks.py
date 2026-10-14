#!/usr/bin/env python3
"""
Update experiment configs with Phase 1 task lists.

Phase 1 includes:
- property_calculation_advanced (20 tasks)
- property_calculation_basic (51 tasks)
"""

import sys
from pathlib import Path
import yaml


# Phase 1 task lists
PHASE1_TASKS = {
    'property_calculation_advanced': [
        'property_calculation_advanced_001_free_energy',
        'property_calculation_advanced_002_crystal_phase',
        'property_calculation_advanced_003_hbond_count',
        'property_calculation_advanced_004_ir_top2_frequencies',
        'property_calculation_advanced_005_crystal_density',
        'property_calculation_advanced_006_cocrystal_ratio',
        'property_calculation_advanced_007_polymorph_free_energy_crossover',
        'property_calculation_advanced_008_interaction_binding_energy',
        'property_calculation_advanced_009_homo_lumo_gap',
        'property_calculation_advanced_010_hbond_distances',
        'property_calculation_advanced_011_accessible_pore_volume_ratio',
        'property_calculation_advanced_012_carboxyl_hydrogen_distance',
        'property_calculation_advanced_013_halogen_bond_energy',
        'property_calculation_advanced_014_bay069_pka',
        'property_calculation_advanced_015_formaldehyde_socme',
        'property_calculation_advanced_016_anthracene_isc_rate',
        'property_calculation_advanced_017_biacetyl_phosphorescence_rate',
        'property_calculation_advanced_018_anthracene_ht_contribution',
        'property_calculation_advanced_019_acetophenone_isc_rate',
        'property_calculation_advanced_020_azulene_internal_conversion_rate',
    ],
    'property_calculation_basic': [
        'property_calculation_basic_001_toluene_aqueous_solvation_free_energy',
        'property_calculation_basic_002_ethanol_aqueous_solvation_free_energy',
        'property_calculation_basic_003_diethyl_ether_aqueous_solvation_free_energy',
        'property_calculation_basic_004_anisole_aqueous_solvation_free_energy',
        'property_calculation_basic_005_nitrobenzene_reduction_potential',
        'property_calculation_basic_006_tetracyanoethylene_reduction_potential',
        'property_calculation_basic_007_dimethylaniline_oxidation_potential',
        'property_calculation_basic_008_triphenylamine_oxidation_potential',
        'property_calculation_basic_009_thianthrene_oxidation_potential',
        'property_calculation_basic_010_water_dimer_binding_energy',
        'property_calculation_basic_011_ammonia_dimer_binding_energy',
        'property_calculation_basic_012_benzene_t_dimer_binding_energy',
        'property_calculation_basic_013_adenine_thymine_wc_pair_binding_energy',
        'property_calculation_basic_014_water_methanol_complex_binding_energy',
        'property_calculation_basic_015_ethene_ethyne_t_complex_binding_energy',
        'property_calculation_basic_016_thiophene_polarizability',
        'property_calculation_basic_017_benzene_polarizability',
        'property_calculation_basic_018_octatetraene_polarizability',
        'property_calculation_basic_019_dimethyl_sulfoxide_water_dipole_moment',
        'property_calculation_basic_020_cis_dichloroethene_dipole_moment',
        'property_calculation_basic_021_acetonitrile_dipole_moment',
        'property_calculation_basic_022_naphthalene_bridge_bond_order',
        'property_calculation_basic_023_dimethyl_sulfone_so_bond_order',
        'property_calculation_basic_024_methyl_nitrate_no_bond_order',
        'property_calculation_basic_025_phenol_surface_esp_minimum',
        'property_calculation_basic_026_nitrobenzene_vdw_surface_area',
        'property_calculation_basic_027_pyrrole_surface_esp_variance',
        'property_calculation_basic_028_urea_crystal_density',
        'property_calculation_basic_029_tnt_crystal_density',
        'property_calculation_basic_030_picric_acid_crystal_density',
        'property_calculation_basic_031_allyl_radical_c1_spin_density',
        'property_calculation_basic_032_benzyl_radical_para_c_spin_density',
        'property_calculation_basic_033_phenoxy_radical_o_spin_density',
        'property_calculation_basic_034_indole_c3_fukui_minus',
        'property_calculation_basic_035_chloronitrobenzene_c_fukui_plus',
        'property_calculation_basic_036_furfural_carbonyl_c_fukui_plus',
        'property_calculation_basic_037_benzene_standard_entropy',
        'property_calculation_basic_038_acetonitrile_standard_entropy',
        'property_calculation_basic_039_neopentane_standard_entropy',
        'property_calculation_basic_040_methane_standard_entropy',
        'property_calculation_basic_041_ammonia_standard_entropy',
        'property_calculation_basic_042_carbon_dioxide_standard_entropy',
        'property_calculation_basic_043_acetic_acid_dimerization_enthalpy',
        'property_calculation_basic_044_caffeine_most_negative_mulliken_atom',
        'property_calculation_basic_045_trifluoroacetic_acid_hydrogen_charge',
        'property_calculation_basic_046_methyl_azide_most_negative_mulliken_atom',
        'property_calculation_basic_047_formaldehyde_s1_vertical_excitation_energy',
        'property_calculation_basic_048_acetaldehyde_s1_vertical_excitation_energy',
        'property_calculation_basic_049_acetone_s1_vertical_excitation_energy',
        'property_calculation_basic_050_pyrazine_s1_vertical_excitation_energy',
        'property_calculation_basic_051_formaldehyde_t1_vertical_excitation_energy',
    ]
}


def update_tasks(config_path: Path) -> bool:
    """Update benchmark tasks to Phase 1."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        cases = config.get('experiment', {}).get('benchmark', {}).get('cases', [])

        # Check if already Phase 1 tasks
        has_phase1 = any(
            case.get('track') in PHASE1_TASKS
            for case in cases
        )

        if has_phase1 and len(cases) == 2:
            # Already has Phase 1, check if complete
            all_correct = True
            for case in cases:
                track = case.get('track')
                if track in PHASE1_TASKS:
                    expected = PHASE1_TASKS[track]
                    actual = case.get('task_ids', [])
                    if actual != expected:
                        all_correct = False
                        break

            if all_correct:
                print(f"  {config_path.relative_to(Path.cwd())} (already Phase 1)")
                return False

        # Update to Phase 1 tasks
        new_cases = [
            {
                'track': 'property_calculation_advanced',
                'task_ids': PHASE1_TASKS['property_calculation_advanced']
            },
            {
                'track': 'property_calculation_basic',
                'task_ids': PHASE1_TASKS['property_calculation_basic']
            }
        ]

        config['experiment']['benchmark']['cases'] = new_cases

        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"✓ {config_path.relative_to(Path.cwd())}")
        print(f"  - Updated to Phase 1: 20 advanced + 51 basic = 71 tasks")
        return True

    except Exception as e:
        print(f"✗ {config_path.relative_to(Path.cwd())}: {e}", file=sys.stderr)
        return False


def main():
    """Update all experiment configs with Phase 1 tasks."""
    repo_root = Path(__file__).parent.parent
    configs_dir = repo_root / 'configs' / 'experiments'

    harnesses = ['openclaw', 'hermes', 'codex', 'claude-code']
    models = ['gpt', 'claude', 'qwen', 'deepseek']

    total = 0
    updated = 0

    print("Updating experiment configs with Phase 1 task lists...\n")
    print("Phase 1: property_calculation_advanced (20) + basic (51) = 71 tasks\n")

    for harness in harnesses:
        harness_dir = configs_dir / harness
        if not harness_dir.exists():
            continue

        for model in models:
            config_file = harness_dir / f'vgb-{model}.config.yaml'
            if config_file.exists():
                total += 1
                if update_tasks(config_file):
                    updated += 1

    print(f"\n{'='*60}")
    print(f"Summary: {updated}/{total} configs updated with Phase 1 tasks")

    if updated > 0:
        print("\nNext steps:")
        print("1. Review: git diff configs/experiments/")
        print("2. Test: source .venv/bin/activate && python -m pytest -m 'not integration' -q")
        print("3. Commit: git add configs/ && git commit -m 'config: update to Phase 1 task lists (71 tasks)'")

    return 0


if __name__ == '__main__':
    sys.exit(main())
