"""Explicit response fields for deterministic pre-comparison test scenarios."""
def object_choice(object_id=None):
    return {'selected_object_id':object_id,
        'considered_objects':([] if object_id is None else [
            {'object_id':object_id,'disposition':'SELECT',
             'reason':'Work on the particular interface selected by this fixture.'}]),
        'no_alternative_reason':(None if object_id is None else
            'Other fixture objects are navigation for separate test tasks; this case examines the selected interface only.')}
