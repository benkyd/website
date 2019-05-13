
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
    }
};
