-- =============================================================================
-- HAMPSTEAD RENOVATIONS VOICE AI AGENT - DATABASE INITIALIZATION
-- =============================================================================
-- PostgreSQL database schema for conversation storage and analytics
-- =============================================================================

-- Create n8n database
CREATE DATABASE hampstead_voice_n8n;

-- Connect to main database (already connected via POSTGRES_DB)
-- \c hampstead_voice

-- =============================================================================
-- EXTENSIONS
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- =============================================================================
-- CONVERSATIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number VARCHAR(20) NOT NULL,
    contact_name VARCHAR(255),
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('whatsapp_text', 'whatsapp_voice', 'phone_call')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'transferred', 'abandoned')),
    lead_score INTEGER CHECK (lead_score >= 0 AND lead_score <= 100),
    lead_tier VARCHAR(10) CHECK (lead_tier IN ('hot', 'warm', 'cold', 'unqualified')),
    hubspot_contact_id VARCHAR(50),
    hubspot_deal_id VARCHAR(50),
    survey_booked BOOLEAN DEFAULT FALSE,
    survey_date TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for conversations
CREATE INDEX idx_conversations_phone ON conversations(phone_number);
CREATE INDEX idx_conversations_channel ON conversations(channel);
CREATE INDEX idx_conversations_started_at ON conversations(started_at);
CREATE INDEX idx_conversations_lead_tier ON conversations(lead_tier);
CREATE INDEX idx_conversations_status ON conversations(status);

-- =============================================================================
-- MESSAGES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text' CHECK (content_type IN ('text', 'audio', 'voice_note')),
    audio_url VARCHAR(500),
    transcript TEXT,
    sentiment VARCHAR(20),
    sentiment_score DECIMAL(3,2),
    tokens_used INTEGER,
    response_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for messages
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_content_trgm ON messages USING gin(content gin_trgm_ops);

-- =============================================================================
-- EXTRACTED INFORMATION TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS extracted_info (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    project_type VARCHAR(100),
    budget_range VARCHAR(50),
    timeline VARCHAR(50),
    postcode VARCHAR(10),
    property_type VARCHAR(50),
    specific_requirements TEXT[],
    contact_email VARCHAR(255),
    preferred_contact_time VARCHAR(50),
    decision_maker BOOLEAN,
    urgency_level VARCHAR(20),
    raw_extraction JSONB,
    confidence_score DECIMAL(3,2),
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for extracted_info
CREATE INDEX idx_extracted_conversation ON extracted_info(conversation_id);
CREATE INDEX idx_extracted_postcode ON extracted_info(postcode);
CREATE INDEX idx_extracted_project_type ON extracted_info(project_type);

-- =============================================================================
-- PHONE CALLS TABLE (VAPI specific)
-- =============================================================================
CREATE TABLE IF NOT EXISTS phone_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    vapi_call_id VARCHAR(100) UNIQUE NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    direction VARCHAR(10) CHECK (direction IN ('inbound', 'outbound')),
    status VARCHAR(20) CHECK (status IN ('ringing', 'in_progress', 'completed', 'failed', 'transferred', 'voicemail')),
    duration_seconds INTEGER,
    recording_url VARCHAR(500),
    transcript TEXT,
    functions_called JSONB DEFAULT '[]',
    transfer_reason TEXT,
    transferred_to VARCHAR(50),
    ended_reason VARCHAR(50),
    cost_cents INTEGER,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for phone_calls
CREATE INDEX idx_calls_vapi_id ON phone_calls(vapi_call_id);
CREATE INDEX idx_calls_phone ON phone_calls(phone_number);
CREATE INDEX idx_calls_status ON phone_calls(status);
CREATE INDEX idx_calls_started_at ON phone_calls(started_at);

-- =============================================================================
-- SURVEY BOOKINGS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS survey_bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    customer_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    email VARCHAR(255),
    address TEXT,
    postcode VARCHAR(10) NOT NULL,
    project_type VARCHAR(100),
    project_description TEXT,
    scheduled_date DATE NOT NULL,
    scheduled_time TIME NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    calendar_event_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'confirmed', 'completed', 'cancelled', 'no_show', 'rescheduled')),
    confirmation_sent BOOLEAN DEFAULT FALSE,
    reminder_sent BOOLEAN DEFAULT FALSE,
    surveyor_notes TEXT,
    outcome VARCHAR(50),
    quoted_amount DECIMAL(10,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for survey_bookings
CREATE INDEX idx_bookings_phone ON survey_bookings(phone_number);
CREATE INDEX idx_bookings_postcode ON survey_bookings(postcode);
CREATE INDEX idx_bookings_scheduled ON survey_bookings(scheduled_date, scheduled_time);
CREATE INDEX idx_bookings_status ON survey_bookings(status);

-- =============================================================================
-- ANALYTICS EVENTS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    phone_number VARCHAR(20),
    channel VARCHAR(20),
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for analytics
CREATE INDEX idx_analytics_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_conversation ON analytics_events(conversation_id);
CREATE INDEX idx_analytics_created_at ON analytics_events(created_at);
CREATE INDEX idx_analytics_properties ON analytics_events USING gin(properties);

-- =============================================================================
-- API METRICS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_metrics (
    id SERIAL PRIMARY KEY,
    endpoint VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms INTEGER NOT NULL,
    request_id VARCHAR(50),
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Partition by month for performance
CREATE INDEX idx_metrics_endpoint ON api_metrics(endpoint);
CREATE INDEX idx_metrics_created_at ON api_metrics(created_at);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to conversations
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to survey_bookings
CREATE TRIGGER update_bookings_updated_at
    BEFORE UPDATE ON survey_bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to calculate lead score
CREATE OR REPLACE FUNCTION calculate_lead_score(
    p_project_type VARCHAR,
    p_budget_range VARCHAR,
    p_timeline VARCHAR,
    p_postcode VARCHAR,
    p_decision_maker BOOLEAN
)
RETURNS INTEGER AS $$
DECLARE
    score INTEGER := 0;
BEGIN
    -- Project type scoring
    IF p_project_type IN ('full_renovation', 'extension', 'loft_conversion') THEN
        score := score + 25;
    ELSIF p_project_type IN ('kitchen', 'bathroom', 'basement') THEN
        score := score + 20;
    ELSIF p_project_type IS NOT NULL THEN
        score := score + 10;
    END IF;
    
    -- Budget scoring
    IF p_budget_range LIKE '%200k%' OR p_budget_range LIKE '%500k%' OR p_budget_range LIKE '%1m%' THEN
        score := score + 25;
    ELSIF p_budget_range LIKE '%100k%' OR p_budget_range LIKE '%150k%' THEN
        score := score + 20;
    ELSIF p_budget_range LIKE '%50k%' OR p_budget_range LIKE '%75k%' THEN
        score := score + 15;
    ELSIF p_budget_range IS NOT NULL THEN
        score := score + 5;
    END IF;
    
    -- Timeline scoring
    IF p_timeline IN ('immediate', '1_month', '2_months') THEN
        score := score + 20;
    ELSIF p_timeline IN ('3_months', '6_months') THEN
        score := score + 15;
    ELSIF p_timeline IS NOT NULL THEN
        score := score + 5;
    END IF;
    
    -- Location scoring (premium areas)
    IF p_postcode ~ '^NW[0-9]' OR p_postcode ~ '^N[0-9]' OR p_postcode ~ '^W[0-9]' THEN
        score := score + 20;
    ELSIF p_postcode IS NOT NULL THEN
        score := score + 10;
    END IF;
    
    -- Decision maker bonus
    IF p_decision_maker = TRUE THEN
        score := score + 10;
    END IF;
    
    RETURN LEAST(score, 100);
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Daily conversation summary
CREATE OR REPLACE VIEW daily_conversation_summary AS
SELECT
    DATE(started_at) as date,
    channel,
    COUNT(*) as total_conversations,
    COUNT(*) FILTER (WHERE lead_tier = 'hot') as hot_leads,
    COUNT(*) FILTER (WHERE lead_tier = 'warm') as warm_leads,
    COUNT(*) FILTER (WHERE survey_booked = TRUE) as surveys_booked,
    AVG(lead_score) as avg_lead_score,
    AVG(EXTRACT(EPOCH FROM (ended_at - started_at))) as avg_duration_seconds
FROM conversations
GROUP BY DATE(started_at), channel
ORDER BY date DESC, channel;

-- Lead funnel view
CREATE OR REPLACE VIEW lead_funnel AS
SELECT
    DATE_TRUNC('week', started_at) as week,
    COUNT(*) as total_conversations,
    COUNT(*) FILTER (WHERE lead_score >= 70) as qualified_leads,
    COUNT(*) FILTER (WHERE survey_booked = TRUE) as surveys_booked,
    COUNT(DISTINCT sb.id) FILTER (WHERE sb.status = 'completed') as surveys_completed,
    COUNT(DISTINCT sb.id) FILTER (WHERE sb.quoted_amount IS NOT NULL) as quotes_given
FROM conversations c
LEFT JOIN survey_bookings sb ON c.id = sb.conversation_id
GROUP BY DATE_TRUNC('week', started_at)
ORDER BY week DESC;

-- =============================================================================
-- INITIAL DATA (Service areas)
-- =============================================================================

-- Create service areas reference table
CREATE TABLE IF NOT EXISTS service_areas (
    id SERIAL PRIMARY KEY,
    postcode_prefix VARCHAR(5) NOT NULL UNIQUE,
    area_name VARCHAR(100),
    travel_time_minutes INTEGER,
    priority_level INTEGER DEFAULT 1 CHECK (priority_level >= 1 AND priority_level <= 3),
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO service_areas (postcode_prefix, area_name, travel_time_minutes, priority_level) VALUES
    ('NW1', 'Camden Town', 10, 1),
    ('NW2', 'Cricklewood', 15, 1),
    ('NW3', 'Hampstead', 5, 1),
    ('NW4', 'Hendon', 20, 1),
    ('NW5', 'Kentish Town', 12, 1),
    ('NW6', 'Kilburn', 10, 1),
    ('NW7', 'Mill Hill', 25, 2),
    ('NW8', 'St Johns Wood', 12, 1),
    ('NW9', 'Kingsbury', 25, 2),
    ('NW10', 'Willesden', 18, 2),
    ('NW11', 'Golders Green', 15, 1),
    ('N1', 'Islington', 18, 2),
    ('N2', 'East Finchley', 15, 1),
    ('N3', 'Finchley', 18, 2),
    ('N4', 'Finsbury Park', 20, 2),
    ('N5', 'Highbury', 20, 2),
    ('N6', 'Highgate', 10, 1),
    ('N7', 'Holloway', 18, 2),
    ('N8', 'Hornsey', 18, 2),
    ('N10', 'Muswell Hill', 15, 1),
    ('N11', 'New Southgate', 25, 2),
    ('N12', 'North Finchley', 22, 2),
    ('W1', 'West End', 25, 2),
    ('W2', 'Paddington', 20, 2),
    ('W3', 'Acton', 30, 3),
    ('W4', 'Chiswick', 35, 3),
    ('W5', 'Ealing', 35, 3),
    ('W6', 'Hammersmith', 30, 3),
    ('W8', 'Kensington', 28, 2),
    ('W9', 'Maida Vale', 15, 1),
    ('W10', 'North Kensington', 22, 2),
    ('W11', 'Notting Hill', 25, 2),
    ('EN4', 'Barnet', 30, 3),
    ('EN5', 'High Barnet', 35, 3)
ON CONFLICT (postcode_prefix) DO NOTHING;

-- =============================================================================
-- PERMISSIONS
-- =============================================================================
-- Grant permissions to application user (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hampstead_app;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hampstead_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO hampstead_app;

COMMIT;
