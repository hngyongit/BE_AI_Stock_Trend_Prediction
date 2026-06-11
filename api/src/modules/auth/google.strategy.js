const passport = require('passport');
const { Strategy: GoogleStrategy } = require('passport-google-oauth20');
const env = require('../../config/env.config');
const authService = require('./auth.service');

/**
 * Register Google OAuth 2.0 strategy when credentials are present.
 */
const registerGoogleStrategy = () => {
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET) {
    return;
  }

  passport.use(
    new GoogleStrategy(
      {
        clientID: env.GOOGLE_CLIENT_ID,
        clientSecret: env.GOOGLE_CLIENT_SECRET,
        callbackURL: env.GOOGLE_CALLBACK_URL,
        passReqToCallback: true
      },
      async (req, _accessToken, _refreshToken, profile, done) => {
        try {
          const signupOnly = req.session?.googleOAuthMode === 'signup';
          const user = await authService.findOrCreateOrLinkGoogleUser(profile, { signupOnly });
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );
};

module.exports = { registerGoogleStrategy };
