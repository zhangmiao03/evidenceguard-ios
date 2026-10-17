"""Validation extracted from the team SeedLite v3 handoff (see UPSTREAM.md).
Text semantics remain unverified even when these constraints pass.
"""
DIRECTIONS = {"left","right","up","down","up_left","up_right","down_left","down_right","stationary","unknown"}

PRESENCE = {'visible', 'occluded', 'out_of_view', 'not_seen', 'unknown'}

CORRESPONDENCE = {'confirmed', 'uncertain', 'unknown'}

REGIONS = {'clear', 'occluded', 'out_of_view', 'unknown'}

ROI_STATES = {'inside', 'outside', 'occluded', 'unknown'}

RELATIONS = {
    'image_plane': {'left_of', 'right_of', 'above', 'below', 'overlaps', 'unknown'},
    'surface': {'on', 'sitting_on', 'inside', 'unknown'},
    'relative_depth': {'in_front_of', 'behind', 'unknown'},
    'region': {'inside_roi', 'outside_roi', 'unknown'},
    'visibility': {'occludes', 'unknown'},
}

def one_of(value, choices):
    return isinstance(value, str) and value in choices

def schema_errors(answer, case, meta, condition):
    errors = []
    if not isinstance(answer, dict):
        return ['answer must be object']
    expected = {'a': meta['frames']['a']}
    if condition != 'A':
        expected['b'] = meta['frames']['b']
    if condition == 'B_upper':
        expected.update({'upper_' + k: v for k, v in meta['upper_frames'].items()})
    observations = answer.get('observations')
    if not isinstance(observations, dict) or set(observations) != set(expected):
        errors.append('observations slots mismatch')
    else:
        for slot, frame in expected.items():
            item = observations[slot]
            if not isinstance(item, dict):
                errors.append(slot + ': observation must be object')
                continue
            for field in ('frame_id', 'camera_id'):
                if item.get(field) != frame[field]:
                    errors.append(slot + ': ' + field + ' mismatch')
            if item.get('target_id') != case['target']['id']:
                errors.append(slot + ': target_id mismatch')
            for field, allowed in [('presence', PRESENCE), ('correspondence', CORRESPONDENCE),
                                   ('roi_state', ROI_STATES), ('region_visibility', REGIONS),
                                   ('occupancy', {'occupied', 'clear', 'unknown'})]:
                if not isinstance(item.get(field), str) or item[field] not in allowed:
                    errors.append(slot + ': invalid ' + field)
            if not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
                errors.append(slot + ': evidence required')
    relations = answer.get('spatial_relations')
    ids = {f['frame_id'] for f in expected.values()}
    if not isinstance(relations, list) or len(relations) > 8:
        errors.append('spatial_relations must be array (max8)')
    else:
        for relation in relations:
            if not isinstance(relation, dict):
                errors.append('relation must be object')
                continue
            category, value = relation.get('category'), relation.get('relation')
            if not isinstance(category, str) or category not in RELATIONS or not isinstance(value, str) or value not in RELATIONS[category]:
                errors.append('invalid relation category/value')
            if not one_of(relation.get('frame_id'), ids):
                errors.append('relation references unavailable frame')
            if not all(isinstance(relation.get(k), str) and relation[k].strip() for k in ('a', 'b', 'evidence')):
                errors.append('relation missing entities/evidence')
    cross = answer.get('cross_frame')
    if not isinstance(cross, dict):
        errors.append('cross_frame required')
    else:
        if cross.get('state_change') not in ('observed_change', 'no_observed_change', 'unknown', 'not_assessed'):
            errors.append('invalid state_change')
        if not one_of(cross.get('image_direction'), DIRECTIONS):
            errors.append('invalid image_direction')
        for key in ('evidence', 'unknowns', 'next_evidence'):
            if not isinstance(cross.get(key), list) or not all(isinstance(v, str) for v in cross[key]):
                errors.append('cross_frame.' + key + ' must be string array')
    if not isinstance(answer.get('summary'), str):
        errors.append('summary required')
    return errors

def evidence_violations(answer, case, meta, condition):
    """Machine-checkable evidence promises. Text semantics still need human review."""
    if not isinstance(answer, dict):
        return []
    cross = answer.get('cross_frame')
    if not isinstance(cross, dict):
        return []
    errors = []
    for field in ('speed', 'distance_m'):
        if field not in cross or cross[field] is not None:
            errors.append(field + '_must_be_null')
    if cross.get('physical_motion') != 'unknown':
        errors.append('unsupported_physical_motion')
    if cross.get('action_claim') != 'unknown':
        errors.append('unsupported_action_claim')
    if cross.get('continuous_tracking_supported') is not False:
        errors.append('unsupported_continuous_tracking')
    if condition == 'A' and (cross.get('state_change') != 'not_assessed' or cross.get('image_direction') != 'unknown'):
        errors.append('single_frame_temporal_claim')
    observations = answer.get('observations', {})
    if not isinstance(observations, dict):
        observations = {}
    b = observations.get('b', {})
    if not isinstance(b, dict):
        b = {}
    if condition != 'A':
        if not meta['gates']['endpoint_comparison_allowed'] and (cross.get('state_change') != 'unknown'
                                                               or cross.get('image_direction') != 'unknown'):
            errors.append('invalid_view_or_time_temporal_claim')
        if meta['gates']['roi_b_source'] == 'invalid' and b.get('roi_state') != 'unknown':
            errors.append('invalid_baseline_roi_reused')
        if (one_of(b.get('presence'), {'occluded', 'out_of_view', 'unknown'}) or b.get('correspondence') != 'confirmed') and cross.get('image_direction') != 'unknown':
            errors.append('motion_without_target_correspondence')
    if condition in ('B_diagnostics', 'B_diagnostics_flow'):
        if meta['flow']['quality']['interpretation_gate'] == 'unreliable_for_object_motion' and cross.get('motion_basis') == 'flow':
            errors.append('unreliable_flow_used_for_motion')
    if not one_of(cross.get('motion_basis'), {'rgb', 'flow', 'none'}):
        errors.append('invalid_motion_basis')
    if condition not in ('B_diagnostics', 'B_diagnostics_flow') and cross.get('motion_basis') == 'flow':
        errors.append('unavailable_flow_used')
    return errors
