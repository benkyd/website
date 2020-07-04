const Logger = require('./logger.js');
const Server = require('./server.js');

const fs = require('fs');

module.exports.serviceRegisterPath = 'services';
module.exports.registeredServices = {};
module.exports.routers = {};

module.exports.init = async function() {
    Logger.info('Initializing service handle')
}

// TODO: This function needs a good ol' referactor
module.exports.registerServices = async function() {
    let json;
    if (!fs.existsSync(__dirname + '/' + module.exports.serviceRegisterPath + '/config.json')) {
        fs.mkdirSync(__dirname + '/' + module.exports.serviceRegisterPath);
        fs.writeFileSync(__dirname + '/' + module.exports.serviceRegisterPath + '/congfig.json', "{}");
        Logger.panic('No service register found!');
    }

    try {
        json = JSON.parse(fs.readFileSync(__dirname + '/' + module.exports.serviceRegisterPath + '/config.json'));
    } catch (e) {
        Logger.panic(`Loading service config failed: ${e}`)
    }

    let services = json; // require(module.exports.serviceRegisterPath);

    if (!services) Logger.panic('There are no services in the register or it was not found');
    
    for ([key, value] of Object.entries(services)) {
        Logger.info(`Loading registered service ${value.name}`);

        try {
            let location = value.location;
            let entryPoint = './' + module.exports.serviceRegisterPath + location + value.entryPoint;
    
            module.exports.registeredServices[key] = require(entryPoint);
            module.exports.routers[key] = {};
            
            let serviceLogger = new Logger.ServiceLogger(value);
            
            // Setup router
            for ([key1, value1] of Object.entries(value.routes)) {
                let routerLocation = './' + module.exports.serviceRegisterPath + location  + value1.router;
                let route = value1.route;
                
                // indexed as [module][route]
                module.exports.routers[key][key1] = require(routerLocation);
                // MODULES MUST EXPORT THE EXPRESS.ROUTER
                Server.app.use(route, module.exports.routers[key][key1]);
            } 
            
            // Calls main of the module with the module, the services logger and
            await module.exports.registeredServices[key].main(value, serviceLogger);
        } catch (e) {
            Logger.error(`Service ${key} failed to load: ${e}`);
        }
    }
    Logger.info('Services initialized');
}

module.exports.reloadServices = async function() {
    // TODO: This
}

module.exports.registeredNewServices = async function() {
    // TODO: This
}
