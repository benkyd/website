
module.exports.serviceRegister = {
    scHost: {
        name: "schost",
        author: "Ben",
        location: "/schost/",
        entryPoint: "index.js",
        routes: {
            image: {
                route: "/image",
                router: "router.js"
            },
            screenshot: {
                route: "/screenshot",
                router: "router.js"
            }
        }
    },
    shortURL: {
        name: 'shorturl',
        author: 'Ben',
        location: '/shorturl/',
        entryPoint: 'index.js',
        routes: {
            url: {
                route: '/url',
                router: 'router.js'
            }
        }
    }
};
