const Logger = require('./logger.js');
const Server = require('./server.js');

const fs = require('fs');

module.exports.serviceRegisterPath = './services';
module.exports.registeredServices = {};
module.exports.routers = {};

module.exports.init = async function() {
    Logger.info('Initialized service handle')
}

module.exports.registerServices = async function() {
    const services = require(module.exports.serviceRegisterPath);
    if (!services.serviceRegister) Logger.panic('There are no services in the register or it was not found');
    
    for ([key, value] of Object.entries(services.serviceRegister)) {
        Logger.info(`Loading registered service ${key}`);

        try {
            let location = value.location;
            let entryPoint = module.exports.serviceRegisterPath + location + value.entryPoint;
    
            module.exports.registeredServices[key] = require(entryPoint);
            module.exports.routers[key] = {};

            // Setup router
            for ([key1, value1] of Object.entries(value.routes)) {
                let routerLocation = module.exports.serviceRegisterPath + location  + value1.router;
                let route = value1.route;

                // indexed as [module][route]
                module.exports.routers[key][key1] = require(routerLocation);
                Server.app.use(route, module.exports.routers[key][key1]);
            } 

            let serviceLogger = new Logger.ServiceLogger(value);

            // Calls main of the module
            await  module.exports.registeredServices[key].main(value, serviceLogger);
        } catch (e) {
            Logger.error(`Service ${key} failed to load: ${e}`);
        }
    }
}

module.exports.reloadServices = async function() {
    // TODO: This
}

module.exports.registeredNewServices = async function() {
    // TODO: This
}
