"""Mobility-domain contract checks for versioned rules and trip provenance."""
from app.db import SessionLocal
from app.models import Trip, TripCalculation, TripEvidence
from test_api import client, login


def test_rules_endpoint_exposes_active_versioned_rule(client):
    rules = client.get('/api/rules')
    assert rules.status_code == 200
    body = rules.json()
    assert body['version'] == '2026.1'
    assert body['baseline_g_per_km'] == 180
    assert body['points_per_kg'] == 10
    assert body['mode_g_per_km'] == {'bus': 70, 'metro': 40, 'bike': 0, 'walk': 0}


def test_trip_persists_rule_snapshot_and_provenance(client):
    headers = login(client)
    response = client.post('/api/trips', headers=headers, json={
        'client_trip_id': 'SIM-TRIP-001',
        'mode': 'bus',
        'distance_km': '12.50',
        'source': 'simulated',
        'evidence_reference': 'demo-device-001',
    })
    assert response.status_code == 200, response.text
    trip = response.json()['trip']
    assert trip['source'] == 'simulated'
    assert trip['rule_version'] == '2026.1'
    assert trip['calculation'] == {
        'baseline_g_per_km': 180,
        'mode_g_per_km': 70,
        'points_per_kg': 10,
    }
    with SessionLocal() as db:
        row = db.get(Trip, trip['id'])
        assert db.get(TripCalculation, row.id).saved_g == 1375
        evidence = db.query(TripEvidence).filter_by(trip_id=row.id).one()
        assert evidence.source_type == 'simulated'
        assert evidence.external_reference == 'demo-device-001'
    detail = client.get(f"/api/trips/{trip['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()['evidence'][0]['external_reference'] == 'demo-device-001'

    registered = client.post('/api/auth/register', json={
        'username': 'tripviewer', 'display_name': '另一位用户', 'password': 'secure-pass-123',
    })
    other_headers = {'Authorization': 'Bearer ' + registered.json()['access_token']}
    assert client.get(f"/api/trips/{trip['id']}", headers=other_headers).status_code == 404


def test_trip_source_is_validated_at_api_boundary(client):
    headers = login(client)
    response = client.post('/api/trips', headers=headers, json={
        'client_trip_id': 'BAD-SOURCE-001',
        'mode': 'bus',
        'distance_km': '10',
        'source': 'unknown-provider',
    })
    assert response.status_code == 422
