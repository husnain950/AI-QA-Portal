import React, { useState } from 'react';
import { LogIn } from 'lucide-react';
import { authApi } from '../utils/auth';

/**
 * Sign-in. Nothing else in the app renders until this succeeds, so it deliberately
 * depends on no store, no router data, and no API call other than the login itself.
 */
export default function LoginPage({ onSignedIn }) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    const submit = async (event) => {
        event.preventDefault();
        setError(null);
        setBusy(true);
        try {
            onSignedIn(await authApi.login(email.trim(), password));
        } catch (err) {
            setError(err.message || 'Sign-in failed');
            setPassword('');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="login-shell">
            <form className="login-card" onSubmit={submit}>
                <h1 className="login-title">PDF-QA Portal</h1>
                <p className="login-subtitle">Sign in to review the corpus.</p>

                {error && (
                    <div className="login-error" role="alert">
                        {error}
                    </div>
                )}

                <div className="form-group">
                    <label className="form-label" htmlFor="login-email">Email</label>
                    <input
                        id="login-email"
                        className="form-input"
                        type="email"
                        autoComplete="username"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                        autoFocus
                    />
                </div>

                <div className="form-group">
                    <label className="form-label" htmlFor="login-password">Password</label>
                    <input
                        id="login-password"
                        className="form-input"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                    />
                </div>

                <button className="btn btn-primary login-submit" type="submit" disabled={busy}>
                    <LogIn size={15} />
                    <span>{busy ? 'Signing in…' : 'Sign in'}</span>
                </button>
            </form>
        </div>
    );
}
