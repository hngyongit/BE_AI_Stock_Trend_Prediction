const passport = require('passport');
const User = require('../database/models/user.model');
const { registerGoogleStrategy } = require('../modules/auth/google.strategy');

/**
 * Wire Passport serialization and Google OAuth strategy.
 */
const configurePassport = () => {
  passport.serializeUser((user, done) => {
    const id = user._id ? user._id.toString() : user.id;
    done(null, id);
  });

  passport.deserializeUser(async (id, done) => {
    try {
      const user = await User.findById(id).populate('role_id');
      done(null, user);
    } catch (err) {
      done(err);
    }
  });

  registerGoogleStrategy();
};

module.exports = configurePassport;
