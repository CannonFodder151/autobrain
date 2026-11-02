# Track Car Mode: Research Findings & Feature Plan

## Executive Summary

Track Car Mode is a specialized driving mode for track/racing use cases, providing enhanced telemetry, real-time performance monitoring, and track-specific insights. This document consolidates research findings, competitor analysis, feature requirements, and implementation plan.

## 1. Research Findings

### 1.1 User Needs (from Reddit/forums patterns)
- **Real-time telemetry**: Users want live lap times, sector times, and delta vs personal best
- **Data logging**: Persistent storage of track sessions for post-session analysis
- **Performance metrics**: G-force, acceleration, braking zones, throttle/brake application
- **Track mapping**: GPS-based track detection and lap counting
- **Battery/thermal monitoring**: Critical for track use (oil temp, coolant, brakes)
- **Simplicity**: Clean UI optimized for in-car use (minimal distraction)
- **Offline capability**: Many tracks have poor connectivity

### 1.2 Market Insights
- Track day enthusiasts value data-driven improvement over vanity metrics
- Integration with existing tools (RaceChrono, Harry's LapTimer, AIM Solo) is important
- Mobile-first solutions dominate; OBD integration adds value
- Users want both real-time feedback and historical analysis

## 2. Competitor Analysis

| Competitor | Strengths | Weaknesses | Opportunity |
|---|---|---|---|
| **RaceChrono** (iOS/Android) | Comprehensive telemetry, great UI, wide sensor support | Paid features, complex setup, platform-locked in some areas | Simpler UX, better integration with existing vehicle health platform |
| **Harry's LapTimer** | Excellent lap timing, track database, affordable | Dated UI, limited social features, less focus on vehicle health | Combine health monitoring + track mode in one app |
| **AIM Solo/Solo DL** | Professional-grade, accurate GPS, great displays | Expensive hardware ($400+), not easily accessible | Software-first approach at lower cost |
| **TrackAddict** | Free tier available, easy to use | Ads in free version, limited advanced analytics | Ad-free experience integrated with AutoBrain ecosystem |
| **Torque Pro** | OBD focus, extensible, cheap | Android-only, complex for beginners, not track-focused | Better UX layer on OBD data with track-specific views |

**Key Differentiator**: AutoBrain can uniquely combine vehicle health monitoring (existing strength) with track performance - no competitor does both well.

## 3. Feature Requirements

### 3.1 MVP Features (Must Have)
- [ ] **Track Mode Toggle**: Enable/disable from dashboard with clear visual indication
- [ ] **Lap Timer**: Auto-detect lap start/finish using GPS or manual triggers
- [ ] **Session Recording**: Record session data (time, laps, basic metrics)
- [ ] **Basic Telemetry Display**: Speed, GPS position, lap count, current lap time
- [ ] **Session History**: View past track sessions
- [ ] **Track Detection**: Basic track recognition or manual track selection

### 3.2 Phase 2 Features (Should Have)
- [ ] **Sector Timing**: Split track into sectors with delta times
- [ ] **Delta Display**: Show time delta vs best lap in real-time
- [ ] **G-Force Meter**: Visual G-force gauge using accelerometer/GPS
- [ ] **Enhanced Vehicle Health**: Track-specific alerts (oil temp, brake wear under stress)
- [ ] **Data Export**: Export to CSV/GPX for use in other tools
- [ ] **Predictive Lap Time**: Estimate final lap time based on current progress

### 3.3 Phase 3 Features (Nice to Have)
- [ ] **Theoretical Best Lap**: Combine best sectors across laps
- [ ] **Video Integration**: Sync with video for analysis
- [ ] **Coaching Insights**: AI-powered suggestions based on driving patterns
- [ ] **Multi-user/Teams**: Share sessions with track day groups
- [ ] **Weather Integration**: Track conditions impact on performance

### 3.4 Non-Functional Requirements
- **Performance**: < 100ms UI updates, minimal battery drain
- **Reliability**: Works offline, syncs when connected
- **Safety**: Minimal UI interaction while driving, voice/large-display optimized
- **Privacy**: User controls data sharing, local-first storage option
- **Compatibility**: Works on mobile browsers, responsive design

## 4. Implementation Plan

### 4.1 Architecture Overview
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Frontend (React)│────▶│  Backend (FastAPI)│────▶│  Storage (DB)   │
│  Track Mode UI   │     │  Track API       │     │  Sessions/Laps  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                        │
         ▼                        ▼
    GPS/Accelerometer      OBD/Vehicle Health
```

### 4.2 Backend Implementation
**New API Endpoints:**
- `POST /api/v1/track/sessions` - Start new track session
- `PUT /api/v1/track/sessions/{id}` - Update session (lap times, telemetry)
- `POST /api/v1/track/sessions/{id}/laps` - Record lap
- `GET /api/v1/track/sessions` - List user sessions
- `GET /api/v1/track/sessions/{id}` - Get session details
- `GET /api/v1/track/tracks` - List known tracks

**New Models/Schemas:**
- `TrackSession`: id, user_id, track_id, start_time, end_time, laps[]
- `Lap`: id, session_id, lap_number, start_time, end_time, lap_time_ms, sectors[]
- `Track`: id, name, location, gps_bounds, sectors[]
- `TelemetryPoint`: timestamp, lat, lng, speed, accel_x, accel_y, accel_z

**Services:**
- `track_session_service.py`: Session management logic
- `lap_detection_service.py`: GPS-based lap detection algorithm
- `track_matching_service.py`: Match GPS coordinates to known tracks

### 4.3 Frontend Implementation
**New Components:**
- `TrackModeScreen.tsx`: Main track mode interface
- `LapTimer.tsx`: Large lap timer display
- `TelemetryPanel.tsx`: Real-time metrics
- `SessionSummary.tsx`: Post-session summary
- `TrackSelector.tsx`: Track selection UI

**New Features Module:**
```
frontend/src/features/trackMode/
├── index.ts
├── TrackModeScreen.tsx
├── components/
│   ├── LapTimer.tsx
│   ├── TelemetryPanel.tsx
│   └── GForceMeter.tsx
├── hooks/
│   ├── useGPS.ts
│   ├── useLapTimer.ts
│   └── useTrackSession.ts
└── api.ts
```

**Integration:**
- Add "Track Mode" nav link in Header
- Add route in App.tsx
- Integrate with existing vehicle health data

### 4.4 Data Model
```sql
track_sessions (
  id UUID PRIMARY KEY,
  user_id UUID,
  track_id UUID,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  status ENUM('active', 'completed', 'aborted'),
  metadata JSONB
);

laps (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES track_sessions(id),
  lap_number INT,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  time_ms INT,
  is_valid BOOLEAN,
  sectors JSONB
);

tracks (
  id UUID PRIMARY KEY,
  name VARCHAR(255),
  country VARCHAR(2),
  gps_center POINT,
  gps_bounds JSONB,
  sector_definitions JSONB
);

telemetry_points (
  id BIGSERIAL PRIMARY KEY,
  session_id UUID REFERENCES track_sessions(id),
  timestamp TIMESTAMP,
  lat DECIMAL(10,8),
  lng DECIMAL(11,8),
  speed_kmh DECIMAL(6,2),
  altitude DECIMAL(8,2),
  accel_x DECIMAL(6,3),
  accel_y DECIMAL(6,3),
  accel_z DECIMAL(6,3)
);
```

## 5. MVP Scope Definition

### 5.1 MVP Deliverables
**Sprint 1 (Week 1-2): Core Infrastructure**
- Backend: Session CRUD APIs
- Frontend: Track mode toggle and basic UI shell
- Data models and migrations
- Basic GPS tracking

**Sprint 2 (Week 3-4): Lap Timing**
- GPS-based lap detection
- Lap timer display
- Session recording
- Basic session history

**Sprint 3 (Week 5-6): Polish & Testing**
- UI optimization for in-car use
- Error handling and offline support
- Testing on mobile devices
- Documentation

### 5.2 MVP Success Criteria
- [ ] User can enable Track Mode from dashboard
- [ ] App detects laps using GPS (within 2-3 second accuracy)
- [ ] Current lap time displays in large, readable format
- [ ] Session saves and appears in history
- [ ] Works on mobile device in landscape mode
- [ ] No impact on existing functionality

### 5.3 Out of Scope for MVP
- Complex sector timing (defer to Phase 2)
- OBD integration (use GPS/phone sensors only for MVP)
- Social features
- Video sync
- Advanced analytics
- Multi-user accounts (assume single user for MVP)

## 6. Technical Considerations

### 6.1 GPS Accuracy
- Use high-accuracy GPS mode
- Implement smoothing/filtering to reduce noise
- Consider geofencing with buffer zones for lap detection
- Fallback to manual lap button if GPS unreliable

### 6.2 Performance
- Throttle telemetry point recording (1-2Hz sufficient)
- Use efficient data structures for real-time updates
- Lazy load session history
- Optimize for low-end mobile devices

### 6.3 Battery Optimization
- Reduce GPS polling when not moving
- Use wake locks sparingly
- Background recording considerations
- Warn users about battery usage

### 6.4 Safety & Legal
- UI must be glanceable (large fonts, high contrast)
- Discourage interaction while moving (or require passenger)
- Comply with local laws regarding device usage while driving
- Clear disclaimer about track use only

## 7. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| GPS accuracy issues | High | High | Implement manual lap trigger, use multiple detection methods |
| Battery drain | High | High | Optimize polling, add battery warnings, test extensively |
| Distraction while driving | High | Medium | Large UI, minimal interactions, passenger-mode focus |
| Track boundary false triggers | Medium | High | Require multiple points to cross, add debounce logic |
| Poor network at track | Medium | High | Offline-first design, sync on reconnect |

## 8. Next Steps

1. **Validate with users**: Share plan with track day community for feedback
2. **Prototype lap detection**: Build proof-of-concept with GPS data
3. **Design UI mockups**: Create in-car optimized designs
4. **Technical spike**: Test GPS accuracy and battery impact
5. **Get approval**: Review with stakeholders before starting implementation

## Appendix

### A. Reference Links
- RaceChrono: https://racechrono.com/
- Harry's LapTimer: https://www.gps-laptimer.de/
- AIM Sports: https://www.aim-sportline.com/

### B. Glossary
- **Lap**: One complete circuit of a track
- **Sector**: A divided portion of a track for timing
- **Delta**: Time difference compared to reference lap
- **Telemetry**: Real-time data from vehicle/sensors
