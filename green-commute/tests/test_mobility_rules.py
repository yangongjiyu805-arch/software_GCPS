"""Operational rule-version management for the mobility domain."""
from test_api import client, login, trip


def test_admin_can_publish_rule_and_new_trip_keeps_version_snapshot(client):
    admin = login(client, 'admin')
    resident = login(client)
    first = trip(client, resident, trip_id='RULE-OLD-001', distance='10')
    assert first.json()['trip']['rule_version'] == '2026.1'
    payload = {
        'version': '2026.2',
        'name': 'GreenGo 调整版模拟规则',
        'baseline_g_per_km': 190,
        'points_per_kg': 10,
        'mode_g_per_km': {'bus': 75, 'metro': 42, 'bike': 0, 'walk': 0},
    }
    published = client.post('/api/admin/rules', headers=admin, json=payload)
    assert published.status_code == 201, published.text
    listed = client.get('/api/admin/rules', headers=admin)
    assert listed.status_code == 200
    assert listed.json()[0]['version'] == '2026.2'
    second = trip(client, resident, trip_id='RULE-NEW-001', distance='10')
    assert second.json()['trip']['rule_version'] == '2026.2'
    assert second.json()['trip']['calculation']['baseline_g_per_km'] == 190
    old = client.get('/api/trips', headers=resident).json()
    snapshots = {item['client_trip_id']: item['rule_version'] for item in old}
    assert snapshots['RULE-OLD-001'] == '2026.1'
    assert snapshots['RULE-NEW-001'] == '2026.2'


def test_rule_management_is_admin_only_and_validates_modes(client):
    resident = login(client)
    payload = {
        'version': '2026.3', 'name': '无权限规则', 'baseline_g_per_km': 180,
        'points_per_kg': 10, 'mode_g_per_km': {'bus': 70, 'metro': 40, 'bike': 0, 'walk': 0},
    }
    assert client.post('/api/admin/rules', headers=resident, json=payload).status_code == 403
    admin = login(client, 'admin')
    bad = {**payload, 'version': '2026.4', 'mode_g_per_km': {'bus': 70}}
    assert client.post('/api/admin/rules', headers=admin, json=bad).status_code == 400
