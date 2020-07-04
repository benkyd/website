const Logger = require('../logger.js');
const Database = require('./authenticatordatabase.js');

module.exports.init = async function() {
    await Database.init();
}

// Only calls next if auth passes
// otherwise, the login / signup
// page is served until a good token
// is provided
module.exports.authenticator = async function(req, res, next) {
    Logger.middleware('auth', 'New authentication request');

    

    next();
}

