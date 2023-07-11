const Database = require('./database.js');

module.exports.genEndpoint = async function() {
    const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

    let endpoint;
    while (true) {
        endpoint = 'U';
        for (let i = 0; i < 7; i++)
            endpoint += possible[Math.floor(Math.random() * possible.length)];

        if (await Database.getURLFromEndpoint(endpoint) == -1)
            break;
    }

    return endpoint;
}

