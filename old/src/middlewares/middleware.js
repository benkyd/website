const Logger = require('../logger.js');

const Auth = require('./authenticator')

module.exports.init = async function() {
    Logger.info('Middewares starting up');
    Logger.middleware('master', 'Middlewares initialising')
    await Auth.init()
}

module.exports.middleware = require('./authenticator.js');
