import { useState, type FormEvent } from "react";
import { Button, Card, Input, Typography, Alert } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { login } from "../api";
import { storeSession, consumeSessionAbsence, type Session } from "../auth";

const { Title, Text } = Typography;

interface LoginScreenProps {
  /** Called after a successful sign-in so the parent can re-read the session. */
  onSignedIn: (session: Session) => void;
}

/**
 * Full-page sign-in screen.  Shown when there is no valid session;
 * the application shell is not rendered behind it.
 */
export function LoginScreen({ onSignedIn }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Consumed once so the notice shows only on the first render after expiry.
  const [absence] = useState(() => consumeSessionAbsence());

  const canSubmit = username.trim().length > 0 && password.length > 0;

  async function handleSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSubmit || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await login(username.trim(), password);
      const session: Session = {
        accessToken: res.access_token,
        expiresAt: res.expires_at,
        role: res.role,
        name: res.name,
      };
      storeSession(session);
      onSignedIn(session);
    } catch {
      // The server deliberately does not distinguish "unknown user" from
      // "wrong password", and the UI must not undo that. One message.
      setError("That username and password do not match.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <Card className="login-card">
        <div className="login-header">
          <div className="brand-mark login-brand-mark" aria-hidden="true">PV</div>
          <Title level={3} style={{ margin: 0 }}>
            PolicyVerbAItim
          </Title>
          <Text type="secondary">AI to read. Evidence to prove. Determinism to decide.</Text>
        </div>

        <form onSubmit={handleSubmit}>
          {absence === "expired" && !error && (
            <Alert
              type="info"
              title="Your session expired. Sign in again to continue where you left off."
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          {error && (
            <Alert
              type="error"
              title={error}
              showIcon
              closable
              onClose={() => setError(null)}
              style={{ marginBottom: 16 }}
            />
          )}

          <div style={{ marginBottom: 12 }}>
            <Input
              prefix={<UserOutlined />}
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              size="large"
              aria-label="Username"
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onPressEnter={() => handleSubmit()}
              size="large"
              aria-label="Password"
            />
          </div>

          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            disabled={!canSubmit}
          >
            Sign in
          </Button>
        </form>
      </Card>
    </div>
  );
}
