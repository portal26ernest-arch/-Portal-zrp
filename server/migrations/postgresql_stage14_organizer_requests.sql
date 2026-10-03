-- Add immutable Organizer Director Request history with one mutable request card.
BEGIN;

CREATE OR REPLACE FUNCTION portal_production_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.kind IN ('chat_messages','chat_pins','chat_attachments') THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'production history is immutable';
    END IF;

    IF OLD.kind NOT IN ('batches','tasks','permissions','settings','access_sessions','work_timers','products','organizer_tasks','organizer_requests')
       OR OLD.id <> NEW.id
       OR OLD.company_id <> NEW.company_id
       OR OLD.kind <> NEW.kind
       OR OLD.created_at <> NEW.created_at THEN
        RAISE EXCEPTION 'production history is immutable';
    END IF;
    RETURN NEW;
END;
$$;

INSERT INTO portal_production_migrations(company_id,version,applied_at)
SELECT id,14,CURRENT_TIMESTAMP::text FROM companies
ON CONFLICT(company_id,version) DO NOTHING;

COMMIT;
