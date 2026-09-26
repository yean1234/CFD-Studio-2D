"""Pre-run physical contract and numerical acceptance criteria, not PH3 calibration."""
import hashlib
import json
import math

CRITERIA = {
    'mass_relative_drift_max': 1e-8,
    'minimum_concentration': -1e-10,
    'analytic_rmse_max': .002,
    'sorption_analytic_rmse_max': .002,
    'restart_max_abs_difference': 1e-10,
    'zero_rates_equivalence_max': 1e-12,
    'refinement_errors_strictly_decreasing': True,
    'experimental_validation': 'blocked_until_independent_data_and_conditions_available',
}


def sorption_parameters(parameters):
    value=parameters.get('adsorption',False)
    if value is False:
        return None
    required={'model','k_ads_s_inv','k_des_s_inv','initial_bulk_Q','evidence'}
    if not isinstance(value,dict) or set(value)!=required:
        raise ValueError('Adsorption requires an explicit model, both rates, initial Q and evidence')
    if value['model']!='linear_reversible' or value['evidence']!='numerical_test_assumption':
        raise ValueError('Only the normalized linear sorption benchmark is supported')
    for key in ['k_ads_s_inv','k_des_s_inv','initial_bulk_Q']:
        v=value[key]
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or v<0:
            raise ValueError('Sorption coefficients and initial Q must be finite and nonnegative')
    return value


def contract(parameters, kind, dt):
    if parameters.get('model_kind', 'normalized_tracer') != 'normalized_tracer':
        raise ValueError('PH3 material model is not implemented or validated; tracer only')
    if parameters.get('target_species', 'PH3') != 'PH3':
        raise ValueError('This research protocol has PH3 as the final target only')
    sorption=sorption_parameters(parameters)
    if sorption and kind!='porous':
        raise ValueError('Sorption tests require an explicitly defined porous domain')
    for key in ['bag_resistance','leakage']:
        if parameters.get(key, False) is not False:
            raise ValueError(f'{key} is not implemented')
    source = source_parameters(parameters)
    termination = termination_parameters(parameters)
    if parameters.get('boundary', 'sealed_no_flux') != 'sealed_no_flux':
        raise ValueError('Only sealed no-flux boundaries supported')
    allowed = {'evidence','lengths_m','transverse_cells','porous_x_fraction','porous_boxes_m',
               'porosity','D_air_m2_s','K_porous_m2_s','end_s','write_interval_s',
               'initial_mean','initial_cosine_amplitude','model_kind','target_species',
               'adsorption','bag_resistance','leakage','source','boundary','termination'}
    unknown=set(parameters)-allowed
    if unknown:
        raise ValueError(f'Unknown input fields: {sorted(unknown)}')
    return {
        'target_species': 'PH3', 'represented_species': 'normalized_inert_tracer',
        'phase_model': 'single_gas_phase', 'concentration': 'pore C/C_ref',
        'initial_condition': {'mean':parameters['initial_mean'],
                              'cosine_amplitude':0 if kind=='uniform' else parameters['initial_cosine_amplitude'],
                              'formula':'mean + amplitude*cos(pi*x/Lx)'},
        'supply':source or {'position':None,'time_function':'0 for all t','enabled':False},
        'termination':termination,
        'walls': 'impermeable; zero normal concentration gradient; U=0',
        'sheet': 'outer sealed boundary approximation; not a separate material',
        'leak': 'absent; flux identically zero',
        'adsorption': sorption or 'disabled', 'bag_resistance':'disabled',
        'sorbed_variable': 'Q per bulk volume / C_ref; not concentration per kg of rice',
        'physical_end_s':parameters['end_s'], 'calculation_dt_s':dt,
        'field_output_interval_s':parameters['write_interval_s'],
        'insects': 'absent', 'concentration_sampling':'offline postprocessing only',
        'experimental_reproduction':False,
    }


def source_parameters(parameters):
    value = parameters.get('source', 'none')
    if value == 'none':
        return None
    required = {'box_m', 'end_s', 'rate_Cref_per_s', 'evidence'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Source requires a box, finite pulse duration, normalized rate and evidence')
    if value['evidence'] != 'numerical_test_assumption':
        raise ValueError('Only normalized tracer supply is validated, not PH3 dosing')
    for key in ['end_s', 'rate_Cref_per_s']:
        v = value[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError('Supply duration and rate must be finite and positive')
    if value['end_s'] > parameters['end_s']:
        raise ValueError('Supply cannot exceed the simulation time limit')
    if parameters['initial_mean'] != 0 or parameters['initial_cosine_amplitude'] != 0:
        raise ValueError('Supply cases start with zero concentration at t=0')
    ads = sorption_parameters(parameters)
    if ads and ads['initial_bulk_Q'] != 0:
        raise ValueError('Supply cases start with zero sorbed inventory')
    return value


def termination_parameters(parameters):
    value = parameters.get('termination', {'mode': 'time'})
    if value == {'mode': 'time'}:
        return value
    required = {'mode', 'relative_rate_per_s', 'absolute_rate_per_s', 'hold_s', 'minimum_time_s'}
    if not isinstance(value, dict) or set(value) != required or value['mode'] != 'steady':
        raise ValueError('Steady termination requires explicit rate tolerances, hold time and minimum time')
    for key in required - {'mode'}:
        v = value[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError('Steady criteria must be finite and positive')
    if value['minimum_time_s'] + value['hold_s'] > parameters['end_s']:
        raise ValueError('Time limit is shorter than the steady qualification window')
    return value


def fingerprint(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,allow_nan=False).encode()).hexdigest()
