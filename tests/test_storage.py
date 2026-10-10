from interactive_surface.storage import Store


def test_save_read_and_reset(tmp_path):
    store=Store(tmp_path/'nested'/'calibration.json')
    assert store.read()=={}
    store.write({'camera_id':'test','camera_quad':[[0,0],[1,0],[1,1],[0,1]]})
    assert store.read()['camera_id']=='test'
    assert store.read()['schema']==1
    store.clear()
    assert store.read()=={}


def test_reject_unsupported_schema(tmp_path):
    store=Store(tmp_path/'broken.json')
    store.path.write_text('{"schema":111}')
    assert store.read()=={}
