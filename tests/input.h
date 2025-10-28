/**
 * Test
 * @nb extra: 'nb::intrusive_ptr<Test>([](Test* o, PyObject* po) noexcept { o->set_self_py(po); }'
 */
class Test
{
  public:
    /**
     * Construct a new Test object
     * @nb
     */
    Test();

    /**
     * Construct a new Test object
     *
     * @nb
     */
    Test(int &a);

    /**
     * Complex parameters
     *
     * @param a a
     * @param b b
     * @param c c
     * @nb
     */
    void nontrivial_params(std::vector<std::string> &a, double *b = nullptr,
                           std::vector<int> &c = std::vector<int>());

    /**
     * An overloaded function
     *
     * @param a First param
     * @nb
     */
    void overload(double &a);

    /**
     * An overloaded function
     *
     * @param b Alternate param
     * @nb
     */
    void overload(int b);

    /**
     * A magic method
     * @nb name: __magic__
     */
    void magic();

    /**
     * An overloaded magic function
     *
     * @param a First param
     * @nb name: __magico__
     */
    void overload_magic(double &a);

    /**
     * An overloaded magic function
     *
     * @param b Alternate param
     * @nb name: __magico__
     */
    void overload_magic(int b);

    /**
     * Static property
     * @nb prop_r: static_property
     */
    static void static_property();


    static int static_method();
};

/**
 * Second class
 * @nb inherit: Test
 */
class Test2
{
  public:

    /**
     * Modified constructor
     * 
     * @param a p1
     * @return nb::ref<Test2> 
     * @nb new
     */
    static nb::ref<Test2> make(int a);

    /**
     * Get the name object
     *
     * @return The name
     * @nb prop_r: name
     */
    std::string get_name();

    /**
     * Set the name object
     *
     * @param name The name
     * @nb prop_w: name
     */
    void set_name(std::string name);

    /**
     * Read-only property
     * @nb prop_r: prop
     */
    void get_prop();

    /**
     * Iterate through this list
     *
     * @return iterator
     * @nb name: __iter__, extra: 'nb::keep_alive<0, 1>()'
     */
    auto iter() -> nb::typed<nb::iterator, ref<Test>&>;
};

/**
 * Don't bind this function you silly program
 *
 */
void dontbind();

/**
 * A free function
 *
 * @param a Hello
 * @param b Bye
 * @return Fye
 * @nb
 */
void free(int a, double b);

/**
 * A simple return type
 *
 * @return Simple return type
 * @nb
 */
int free_return_simple();

/**
 * Enum example
 * @nb
 */
enum class TestEnum : std::uint8_t
{
    CAR,
    TRUCK,
    BIKE
};

/**
 * An unbound enum
 */
enum class DontBind 
{
    DO,
    NOT,
    BIND
};